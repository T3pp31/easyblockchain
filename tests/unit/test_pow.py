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


def test_get_difficulty_does_not_raise_on_non_string_block_item():
    settings = PowSettings(initial_difficulty=4, adjustment_interval=2, target_block_time_seconds=10)
    pow_algo = ProofOfWork(settings)
    chain = [
        {"block_header": {"difficulty": 4}, "block_item": None},
        {"block_header": {"difficulty": 4}, "block_item": "2026-01-01 00:00:10"},
    ]
    difficulty = pow_algo.get_difficulty(chain)
    assert isinstance(difficulty, int)
    assert difficulty >= 1


def test_get_difficulty_does_not_raise_on_non_string_end_block_item():
    # Given: 末尾ブロックの block_item が非文字列（int 等）
    # When: get_difficulty を呼ぶ
    # Then: 例外ではなくフォールバック経由の難易度が返る
    settings = PowSettings(initial_difficulty=4, adjustment_interval=2, target_block_time_seconds=10)
    pow_algo = ProofOfWork(settings)
    chain = [
        {"block_header": {"difficulty": 4}, "block_item": "2026-01-01 00:00:00"},
        {"block_header": {"difficulty": 4}, "block_item": 123},
    ]
    difficulty = pow_algo.get_difficulty(chain)
    assert isinstance(difficulty, int)
    assert difficulty >= 1


def test_elapsed_seconds_falls_back_to_target_times_interval():
    # Given: block_item が非文字列のブロック
    # When: _elapsed_seconds を呼ぶ
    # Then: フォールバック値 target_block_time_seconds * adjustment_interval を返す
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=4, adjustment_interval=2, target_block_time_seconds=10))
    bad_start = {"block_header": {}, "block_item": None}
    valid_end = {"block_header": {}, "block_item": "2026-01-01 00:00:10"}
    assert pow_algo._elapsed_seconds(bad_start, valid_end) == 20
    assert pow_algo._elapsed_seconds(valid_end, bad_start) == 20


def test_elapsed_seconds_parses_valid_block_items():
    # Given: 有効な block_item のペア
    # When: _elapsed_seconds を呼ぶ
    # Then: 実際の経過秒を返す
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=4, adjustment_interval=2, target_block_time_seconds=10))
    start = {"block_header": {}, "block_item": "2026-01-01 00:00:00"}
    end = {"block_header": {}, "block_item": "2026-01-01 00:00:10"}
    assert pow_algo._elapsed_seconds(start, end) == 10


def test_elapsed_seconds_falls_back_on_unparsable_format():
    # Given: 書式不正の block_item
    # When: _elapsed_seconds を呼ぶ
    # Then: フォールバック値を返す
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=4, adjustment_interval=2, target_block_time_seconds=10))
    bad = {"block_header": {}, "block_item": "not-a-timestamp"}
    valid = {"block_header": {}, "block_item": "2026-01-01 00:00:10"}
    assert pow_algo._elapsed_seconds(bad, valid) == 20
    assert pow_algo._elapsed_seconds(valid, bad) == 20
