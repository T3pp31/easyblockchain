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


def test_validate_block_rejects_declared_difficulty_mismatch():
    pow_algo = ProofOfWork(PowSettings())
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
    assert result.reason == "difficulty does not match network expectation"


def test_validate_block_accepts_expected_difficulty(pow_blockchain):
    block = pow_blockchain.add_new_block(["a"], ["b"])
    result = pow_blockchain.consensus.validate_block(block, pow_blockchain.chain[:-1])
    assert result.valid is True


def test_meets_difficulty_rejects_non_positive_difficulty():
    assert not meets_difficulty("0" * 64, 0)
    assert not meets_difficulty("0" * 64, -1)


def test_validate_block_rejects_non_numeric_difficulty():
    pow_algo = ProofOfWork(PowSettings())
    block = {
        "block_header": {
            "prev_hash": "0" * 64,
            "tran_hash": "0" * 64,
            "consensus_type": "pow",
            "nonce": 0,
            "difficulty": "abc",
        },
        "tran_body": {"input_data": [], "output_data": []},
    }
    result = pow_algo.validate_block(block, [])
    assert result.valid is False
    assert result.reason == "invalid difficulty"


def test_validate_block_rejects_none_difficulty():
    pow_algo = ProofOfWork(PowSettings())
    block = {
        "block_header": {
            "prev_hash": "0" * 64,
            "tran_hash": "0" * 64,
            "consensus_type": "pow",
            "nonce": 0,
            "difficulty": None,
        },
        "tran_body": {"input_data": [], "output_data": []},
    }
    result = pow_algo.validate_block(block, [])
    assert result.valid is False
    assert result.reason == "invalid difficulty"


def test_validate_block_rejects_non_numeric_nonce():
    pow_algo = ProofOfWork(PowSettings())
    block = {
        "block_header": {
            "prev_hash": "0" * 64,
            "tran_hash": "0" * 64,
            "consensus_type": "pow",
            "nonce": "abc",
            "difficulty": 4,
        },
        "tran_body": {"input_data": [], "output_data": []},
    }
    result = pow_algo.validate_block(block, [])
    assert result.valid is False
    assert result.reason == "invalid nonce"


def test_get_difficulty_decreases_when_mining_is_slow():
    settings = PowSettings(
        initial_difficulty=4,
        adjustment_interval=2,
        target_block_time_seconds=10,
    )
    pow_algo = ProofOfWork(settings)
    chain = [
        {"block_header": {"difficulty": 4}, "block_item": "2026-01-01 00:00:00"},
        {"block_header": {"difficulty": 4}, "block_item": "2026-01-01 00:02:00"},
    ]
    assert pow_algo.get_difficulty(chain) == 2


def test_get_difficulty_increases_when_mining_is_fast():
    settings = PowSettings(
        initial_difficulty=4,
        adjustment_interval=2,
        target_block_time_seconds=10,
    )
    pow_algo = ProofOfWork(settings)
    chain = [
        {"block_header": {"difficulty": 4}, "block_item": "2026-01-01 00:00:00"},
        {"block_header": {"difficulty": 4}, "block_item": "2026-01-01 00:00:05"},
    ]
    assert pow_algo.get_difficulty(chain) == 8


def test_get_difficulty_slow_adjustment_is_capped():
    settings = PowSettings(
        initial_difficulty=8,
        adjustment_interval=2,
        target_block_time_seconds=10,
    )
    pow_algo = ProofOfWork(settings)
    chain = [
        {"block_header": {"difficulty": 8}, "block_item": "2026-01-01 00:00:00"},
        {"block_header": {"difficulty": 8}, "block_item": "2026-01-01 01:00:00"},
    ]
    assert pow_algo.get_difficulty(chain) == 4


def test_get_difficulty_slow_partial_decrease():
    # Given: ratio = 1.5（cap 未満の部分的な遅さ）
    # When: get_difficulty を呼ぶ
    # Then: ratio 自身で割った値（6 / 1.5 = 4）になる
    settings = PowSettings(
        initial_difficulty=6,
        adjustment_interval=2,
        target_block_time_seconds=10,
    )
    pow_algo = ProofOfWork(settings)
    chain = [
        {"block_header": {"difficulty": 6}, "block_item": "2026-01-01 00:00:00"},
        {"block_header": {"difficulty": 6}, "block_item": "2026-01-01 00:00:15"},
    ]
    assert pow_algo.get_difficulty(chain) == 4


def test_get_difficulty_no_adjustment_at_target_time():
    # Given: ブロック間隔が目標どおり（ratio = 1.0）
    # When: get_difficulty を呼ぶ
    # Then: 難易度は無調整（initial と同じ値を維持）
    settings = PowSettings(
        initial_difficulty=4,
        adjustment_interval=2,
        target_block_time_seconds=10,
    )
    pow_algo = ProofOfWork(settings)
    chain = [
        {"block_header": {"difficulty": 4}, "block_item": "2026-01-01 00:00:00"},
        {"block_header": {"difficulty": 4}, "block_item": "2026-01-01 00:00:10"},
    ]
    assert pow_algo.get_difficulty(chain) == 4


def test_get_difficulty_slow_decrease_never_exceeds_cap():
    # Given: first_difficulty=3 で切り捨てが発生するケース（3 / 2 = 1.5 → int で 1）
    # When: get_difficulty を呼ぶ
    # Then: 低下幅度は max_adjustment_factor 以内（3 → 2、1.5 倍）に収まる
    settings = PowSettings(
        initial_difficulty=3,
        adjustment_interval=2,
        target_block_time_seconds=10,
    )
    pow_algo = ProofOfWork(settings)
    chain = [
        {"block_header": {"difficulty": 3}, "block_item": "2026-01-01 00:00:00"},
        {"block_header": {"difficulty": 3}, "block_item": "2026-01-01 01:00:00"},
    ]
    assert pow_algo.get_difficulty(chain) == 2


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
