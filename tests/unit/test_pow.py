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


def test_validate_block_rejects_earlier_block_item_than_parent(pow_blockchain):
    pow_blockchain.add_new_block(["a"], ["b"])
    pow_blockchain.add_new_block(["c"], ["d"])
    block = pow_blockchain.chain[-1]
    chain = pow_blockchain.chain[:-1]
    block["block_item"] = "1999-01-01 00:00:00"
    result = pow_blockchain.consensus.validate_block(block, chain)
    assert result.valid is False
    assert result.reason == "block_item earlier than parent"


def test_validate_block_rejects_missing_block_item():
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=1))
    block = {
        "block_header": {
            "prev_hash": "0" * 64,
            "tran_hash": "0" * 64,
            "consensus_type": "pow",
            "nonce": 0,
            "difficulty": 1,
        },
        "tran_body": {"input_data": [], "output_data": []},
    }
    result = pow_algo.validate_block(block, [])
    assert result.valid is False
    assert result.reason == "missing or invalid block_item"


def test_validate_block_rejects_unparsable_block_item():
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=1))
    block = {
        "block_item": "not-a-timestamp",
        "block_header": {
            "prev_hash": "0" * 64,
            "tran_hash": "0" * 64,
            "consensus_type": "pow",
            "nonce": 0,
            "difficulty": 1,
        },
        "tran_body": {"input_data": [], "output_data": []},
    }
    result = pow_algo.validate_block(block, [])
    assert result.valid is False
    assert result.reason == "invalid block_item format"


def test_validate_block_rejects_invalid_parent_block_item():
    # Given: 親ブロックの block_item がパース不能なチェーン
    # When: validate_block を呼ぶ
    # Then: 単調性を検証できないため fail-closed で拒否される
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=1))
    parent = {
        "block_index": 1,
        "block_item": "not-a-timestamp",
        "block_header": {"prev_hash": "0" * 64, "tran_hash": "1" * 64},
        "tran_body": {"input_data": [], "output_data": []},
    }
    block = {
        "block_item": "2026-01-01 00:00:00",
        "block_header": {
            "prev_hash": "1" * 64,
            "tran_hash": "0" * 64,
            "consensus_type": "pow",
            "nonce": 0,
            "difficulty": 1,
        },
        "tran_body": {"input_data": [], "output_data": []},
    }
    result = pow_algo.validate_block(block, [parent])
    assert result.valid is False
    assert result.reason == "parent block_item missing or invalid"


def test_validate_block_accepts_equal_block_item_than_parent(pow_blockchain):
    # Given: 親と同時刻の block_item を持つ正規ブロック
    # When: validate_block を呼ぶ
    # Then: 検証を通過する
    pow_blockchain.add_new_block(["a"], ["b"])
    pow_blockchain.add_new_block(["c"], ["d"])
    block = pow_blockchain.chain[-1]
    chain = pow_blockchain.chain[:-1]
    block["block_item"] = chain[-1]["block_item"]
    result = pow_blockchain.consensus.validate_block(block, chain)
    assert result.valid is True


def test_validate_block_accepts_later_block_item_than_parent(pow_blockchain):
    # Given: 親より未来の block_item を持つ正規ブロック
    # When: validate_block を呼ぶ
    # Then: 検証を通過する
    pow_blockchain.add_new_block(["a"], ["b"])
    pow_blockchain.add_new_block(["c"], ["d"])
    block = pow_blockchain.chain[-1]
    chain = pow_blockchain.chain[:-1]
    block["block_item"] = "2999-01-01 00:00:00"
    result = pow_blockchain.consensus.validate_block(block, chain)
    assert result.valid is True
