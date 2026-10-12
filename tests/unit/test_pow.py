import pytest

from useful_blockchain.consensus.pow import ProofOfWork
from useful_blockchain.hash_utils import meets_difficulty
from useful_blockchain.types import PowSettings


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


def test_validate_block_missing_fields_rejected_without_error(low_difficulty_pow):
    # Given: tran_body / prev_hash / tran_hash を欠くブロック
    # When: validate_block を呼ぶ
    # Then: 例外ではなく invalid な結果が返る
    block = {
        "block_index": 1,
        "block_header": {"consensus_type": "pow", "nonce": 1, "difficulty": 1},
        "tran_body": {"input_data": ["a"], "output_data": ["b"]},
    }
    result = low_difficulty_pow.validate_block(block, [])
    assert result.valid is False
    assert result.reason == "missing PoW fields"

    no_body = {"block_header": dict(block["block_header"], prev_hash="0" * 64)}
    assert low_difficulty_pow.validate_block(no_body, []).valid is False


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
