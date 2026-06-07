from useful_blockchain.chain_validator import verify_chain_integrity
from useful_blockchain.consensus.pow import ProofOfWork
from useful_blockchain.types import DEFAULT_GENESIS_PREV_HASH, PowSettings


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
