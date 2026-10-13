import pytest

from useful_blockchain.consensus.pow import ProofOfWork
from useful_blockchain.hash_utils import meets_difficulty
from useful_blockchain.types import DEFAULT_GENESIS_PREV_HASH, PowSettings


@pytest.fixture
def low_difficulty_pow():
    return ProofOfWork(PowSettings(initial_difficulty=1, max_mining_iterations=100000))


def test_mine_block_meets_difficulty(low_difficulty_pow, pow_blockchain):
    block = pow_blockchain.add_new_block(["sender"], ["receiver"])
    difficulty = block["block_header"]["difficulty"]
    tran_hash = block["block_header"]["tran_hash"]
    assert meets_difficulty(tran_hash, difficulty)


def test_invalid_nonce_rejected(low_difficulty_pow, pow_blockchain):
    block = pow_blockchain.add_new_block(["a"], ["b"])
    block["block_header"]["nonce"] = block["block_header"]["nonce"] + 1
    result = low_difficulty_pow.validate_block(block, pow_blockchain.chain[:-1])
    assert result.valid is False


def test_difficulty_adjustment():
    settings = PowSettings(
        initial_difficulty=1,
        adjustment_interval=2,
        target_block_time_seconds=1,
        max_mining_iterations=100000,
    )
    pow_algo = ProofOfWork(settings)
    bc = __import__("useful_blockchain.blockchain", fromlist=["BlockChain"]).BlockChain(
        consensus=pow_algo
    )
    bc.add_new_block(["a"], ["b"])
    bc.add_new_block(["c"], ["d"])
    d = pow_algo.get_difficulty(bc.chain)
    assert d >= 1


def test_select_canonical_chain_prefers_longer(low_difficulty_pow, pow_blockchain):
    pow_blockchain.add_new_block(["a"], ["b"])
    short = list(pow_blockchain.chain)
    pow_blockchain.add_new_block(["c"], ["d"])
    long_chain = list(pow_blockchain.chain)
    selected = low_difficulty_pow.select_canonical_chain([short, long_chain])
    assert len(selected) == 2


def test_select_canonical_chain_prefers_cumulative_work_over_length():
    from useful_blockchain.blockchain import BlockChain

    pow_low = ProofOfWork(PowSettings(initial_difficulty=1, max_mining_iterations=500000))
    bc_low = BlockChain(consensus=pow_low)
    for i in range(3):
        bc_low.add_new_block([f"in{i}"], [f"out{i}"])
    pow_high = ProofOfWork(PowSettings(initial_difficulty=2, max_mining_iterations=500000))
    bc_high = BlockChain(consensus=pow_high)
    for i in range(2):
        bc_high.add_new_block([f"in{i}"], [f"out{i}"])

    longer_lower_work = list(bc_low.chain)
    shorter_higher_work = list(bc_high.chain)

    # 前提: BlockChain は初期 chain に genesis を含まないため、
    # チェーン長は採掘ブロック数と一致する（期待値はこれに依存する）
    selected = pow_low.select_canonical_chain([longer_lower_work, shorter_higher_work])
    assert selected is shorter_higher_work
    selected = pow_low.select_canonical_chain([shorter_higher_work, longer_lower_work])
    assert selected is shorter_higher_work
    assert pow_low.score_chain(shorter_higher_work) == (4, 2)
    assert pow_low.score_chain(longer_lower_work) == (3, 3)


def test_select_canonical_chain_excludes_forged_difficulty_chain():
    # Given: difficulty を水増し宣言したが実際の PoW を満たさないブロックのチェーン
    # When: select_canonical_chain を呼ぶ
    # Then: 無効チェーンは選択されない（ヘッダ difficulty に対する PoW 検証の担保）
    from useful_blockchain.blockchain import BlockChain
    from useful_blockchain.hash_utils import calc_body_hash, calc_pow_tran_hash

    pow_algo = ProofOfWork(PowSettings(initial_difficulty=1, max_mining_iterations=500000))
    bc = BlockChain(consensus=pow_algo)
    bc.add_new_block(["a"], ["b"])
    valid_chain = list(bc.chain)

    prev_hash = DEFAULT_GENESIS_PREV_HASH
    body_hash = calc_body_hash({"input_data": ["x"], "output_data": ["y"]})
    real_hash = calc_pow_tran_hash(prev_hash, body_hash, 0)
    forged = [
        {
            "block_index": 1,
            "block_item": "2026-01-01 00:00:00",
            "block_header": {
                "prev_hash": prev_hash,
                "tran_hash": real_hash,
                "consensus_type": "pow",
                "nonce": 0,
                "difficulty": 30,
            },
            "tran_body": {"input_data": ["x"], "output_data": ["y"]},
        }
    ]
    assert pow_algo._is_chain_valid(forged) is False
    selected = pow_algo.select_canonical_chain([valid_chain, forged])
    assert selected == valid_chain
    selected = pow_algo.select_canonical_chain([forged, valid_chain])
    assert selected == valid_chain
