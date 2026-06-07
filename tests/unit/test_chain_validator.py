import pytest

from useful_blockchain.chain_validator import verify_chain_integrity
from useful_blockchain.consensus.pos import ProofOfStake
from useful_blockchain.consensus.pow import ProofOfWork
from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import DEFAULT_GENESIS_PREV_HASH, PosSettings, PowSettings


def _make_block(block_index: int, prev_hash: str, tran_hash: str) -> dict:
    return {
        "block_index": block_index,
        "block_header": {
            "prev_hash": prev_hash,
            "tran_hash": tran_hash,
            "consensus_type": "pow",
            "nonce": 0,
            "difficulty": 1,
        },
        "tran_body": {"input_data": ["a"], "output_data": ["b"]},
    }


def test_verify_chain_valid_genesis():
    # Given: 正しい genesis prev_hash を持つ先頭ブロック
    # When: verify_chain_integrity を呼ぶ
    # Then: 検証成功
    chain = [_make_block(1, DEFAULT_GENESIS_PREV_HASH, "a" * 64)]
    result = verify_chain_integrity(chain)
    assert result.valid is True


def test_verify_chain_invalid_genesis():
    # Given: 不正な genesis prev_hash を持つ先頭ブロック
    # When: verify_chain_integrity を呼ぶ
    # Then: genesis prev_hash mismatch で失敗
    chain = [_make_block(1, "1" * 64, "a" * 64)]
    result = verify_chain_integrity(chain, genesis_prev_hash=DEFAULT_GENESIS_PREV_HASH)
    assert result.valid is False
    assert result.reason == "genesis prev_hash mismatch"
    assert result.failed_at_index == 1


def test_consensus_validate_chain_link_genesis():
    # Given: PoW 合意と先頭ブロック
    # When: validate_chain_link で genesis を検証
    # Then: 一致時は成功、不一致時は失敗
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=1))
    pow_algo.genesis_prev_hash = DEFAULT_GENESIS_PREV_HASH
    block = _make_block(1, DEFAULT_GENESIS_PREV_HASH, "0" * 64)
    link = pow_algo.validate_chain_link(block, None, DEFAULT_GENESIS_PREV_HASH)
    assert link.valid is True
    bad_link = pow_algo.validate_chain_link(block, None, "1" * 64)
    assert bad_link.valid is False
    assert bad_link.reason == "genesis prev_hash mismatch"


@pytest.fixture
def pos_chain_setup():
    settings = PosSettings(min_stake=100, block_reward=10)
    genesis_stakes = {"validator-a": 200, "validator-b": 300}
    instances: dict[str, ProofOfStake] = {}
    for vid in genesis_stakes:
        sm = SignatureManager()
        sm.generate_key_pair()
        pos = ProofOfStake(
            settings,
            node_validator_id=vid,
            signature_manager=sm,
            genesis_stakes=genesis_stakes,
        )
        for v_id, stake in genesis_stakes.items():
            pos.register_validator(v_id, stake)
        instances[vid] = pos
    return genesis_stakes, instances, settings


def test_verify_chain_integrity_pos_with_genesis_stakes(pos_chain_setup):
    # Given: 複数ブロックの PoS チェーンと genesis_stakes
    # When: verify_chain_integrity に genesis_stakes を渡す
    # Then: 再生ベース検証で成功する
    from pos_helpers import build_pos_chain

    genesis_stakes, instances, settings = pos_chain_setup
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=2)
    pos = instances["validator-a"]
    result = verify_chain_integrity(
        chain, pos, DEFAULT_GENESIS_PREV_HASH, genesis_stakes=genesis_stakes
    )
    assert result.valid is True


def test_verify_chain_integrity_pos_without_genesis_stakes_fails_multi_block(
    pos_chain_setup,
):
    # Given: 複数ブロックの PoS チェーン（validators は genesis のみ）
    # When: genesis_stakes なしで検証
    # Then: 2ブロック目以降で失敗しうる
    from pos_helpers import build_pos_chain

    genesis_stakes, _, _ = pos_chain_setup
    settings = PosSettings(epoch_length=1, min_stake=100, block_reward=10)
    instances: dict[str, ProofOfStake] = {}
    for vid in genesis_stakes:
        sm = SignatureManager()
        sm.generate_key_pair()
        pos_instance = ProofOfStake(
            settings,
            node_validator_id=vid,
            signature_manager=sm,
            genesis_stakes=genesis_stakes,
        )
        for v_id, stake in genesis_stakes.items():
            pos_instance.register_validator(v_id, stake)
        instances[vid] = pos_instance
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=2)
    pos = ProofOfStake(settings)
    pos.validators = dict(genesis_stakes)
    result = verify_chain_integrity(chain, pos, DEFAULT_GENESIS_PREV_HASH)
    if len(chain) > 1:
        assert result.valid is False
