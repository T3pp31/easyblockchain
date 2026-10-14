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
