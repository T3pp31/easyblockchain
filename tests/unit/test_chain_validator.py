from __future__ import annotations
from useful_blockchain.hash_utils import calc_pow_tran_hash, meets_difficulty
import pytest

from useful_blockchain.chain_validator import verify_chain_integrity
from useful_blockchain.consensus.pos import ProofOfStake
from useful_blockchain.consensus.pow import ProofOfWork
from useful_blockchain.hash_utils import calc_body_hash, calc_legacy_tran_hash
from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import DEFAULT_GENESIS_PREV_HASH, PosSettings, PowSettings


def _make_block(
    block_index: int,
    prev_hash: str,
    tran_hash: str,
    *,
    consensus_type: str | None = "pow",
) -> dict:
    header: dict = {"prev_hash": prev_hash, "tran_hash": tran_hash}
    if consensus_type is not None:
        header.update({"consensus_type": consensus_type, "nonce": 0, "difficulty": 1})
    return {
        "block_index": block_index,
        "block_header": header,
        "tran_body": {"input_data": ["a"], "output_data": ["b"]},
    }


def test_verify_chain_valid_genesis():
    # Given: 正しい genesis prev_hash を持つレガシー先頭ブロック
    # When: verify_chain_integrity を呼ぶ
    # Then: 検証成功
    block = _make_block(1, DEFAULT_GENESIS_PREV_HASH, "a" * 64)
    block["block_header"].pop("consensus_type")
    block["block_header"]["tran_hash"] = calc_legacy_tran_hash(
        DEFAULT_GENESIS_PREV_HASH, calc_body_hash(block["tran_body"])
    )
    chain = [block]
    result = verify_chain_integrity(chain)
    assert result.valid is True


def test_verify_chain_rejects_consensus_type_without_consensus():
    # Given: consensus_type を持つブロックと合意なしノード
    # When: verify_chain_integrity を呼ぶ
    # Then: consensus_type 付きだが検証器が設定されていないことで失敗
    chain = [_make_block(1, DEFAULT_GENESIS_PREV_HASH, "a" * 64)]
    result = verify_chain_integrity(chain)
    assert result.valid is False
    assert (
        result.reason
        == "consensus_type present but no consensus validator configured"
    )


def test_verify_chain_rejects_empty_string_consensus_type():
    # Given: consensus_type が空文字列のブロック（レガシー扱いにしない）
    # When: verify_chain_integrity を呼ぶ
    # Then: 検証器が設定されていないことで失敗する
    block = _make_block(1, DEFAULT_GENESIS_PREV_HASH, "a" * 64)
    block["block_header"]["consensus_type"] = ""
    chain = [block]
    result = verify_chain_integrity(chain)
    assert result.valid is False
    assert (
        result.reason
        == "consensus_type present but no consensus validator configured"
    )


def test_verify_chain_validates_pow_block_without_consensus_type():
    # Given: PoW 合意と consensus_type を欠くブロック
    # When: verify_chain_integrity を呼ぶ
    # Then: consensus_type is not pow で失敗
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=1))
    block = _make_block(1, DEFAULT_GENESIS_PREV_HASH, "a" * 64)
    block["block_header"].pop("consensus_type")
    result = verify_chain_integrity([block], pow_algo, DEFAULT_GENESIS_PREV_HASH)
    assert result.valid is False
    assert result.reason == "consensus_type is not pow"


def test_verify_chain_validates_pos_block_without_consensus_type(pos_chain_setup):
    # Given: PoS 合意と consensus_type を欠くブロック
    # When: verify_chain_integrity を呼ぶ
    # Then: consensus_type is not pos で失敗
    genesis_stakes, instances, settings = pos_chain_setup
    from pos_helpers import build_pos_chain

    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=1)
    chain[0]["block_header"].pop("consensus_type")
    pos = instances[chain[0]["block_header"]["validator_id"]]
    result = verify_chain_integrity(
        chain, pos, DEFAULT_GENESIS_PREV_HASH, genesis_stakes=genesis_stakes
    )
    assert result.valid is False
    assert result.reason == "consensus_type is not pos"


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
        pos = ProofOfStake(settings, node_validator_id=vid, signature_manager=sm)
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

    genesis_stakes, instances, settings = pos_chain_setup
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=2)
    pos = ProofOfStake(settings)
    pos.validators = dict(genesis_stakes)
    result = verify_chain_integrity(chain, pos, DEFAULT_GENESIS_PREV_HASH)
    if len(chain) > 1:
        assert result.valid is False


def test_verify_chain_rejects_shifted_first_block_index():
    # Given: block_index をずらした先頭ブロック
    # When: verify_chain_integrity を呼ぶ
    # Then: first block_index must be 1 で失敗
    chain = [_make_block(2, DEFAULT_GENESIS_PREV_HASH, "a" * 64)]
    result = verify_chain_integrity(chain)
    assert result.valid is False
    assert result.reason == "first block_index must be 1"
    assert result.failed_at_index == 1


def test_verify_chain_rejects_shifted_first_block_index_with_consensus():
    # Given: PoW 合意と block_index をずらした先頭ブロック
    # When: verify_chain_integrity を呼ぶ
    # Then: first block_index must be 1 で失敗
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=1))
    chain = [_make_block(3, DEFAULT_GENESIS_PREV_HASH, "a" * 64)]
    result = verify_chain_integrity(chain, pow_algo, DEFAULT_GENESIS_PREV_HASH)
    assert result.valid is False
    assert result.reason == "first block_index must be 1"


def test_validate_chain_link_rejects_non_one_first_index(pos_chain_setup):
    # Given: genesis_stakes 付き PoS と block_index=2 の先頭ブロック
    # When: verify_chain_integrity を呼ぶ
    # Then: first block_index must be 1 で失敗
    genesis_stakes, instances, settings = pos_chain_setup
    from pos_helpers import build_pos_chain

    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=1)
    chain[0]["block_index"] = 2
    pos = instances[chain[0]["block_header"]["validator_id"]]
    result = verify_chain_integrity(
        chain, pos, DEFAULT_GENESIS_PREV_HASH, genesis_stakes=genesis_stakes
    )
    assert result.valid is False
    assert result.reason == "first block_index must be 1"


def test_validate_chain_link_rejects_non_one_first_index_direct_pow():
    # Given: PoW 合意実装と block_index=2 の先頭ブロック
    # When: validate_chain_link を直接呼ぶ
    # Then: first block_index must be 1 で失敗（base.py 側の検証を直接担保）
    algo = ProofOfWork(PowSettings(initial_difficulty=1))
    algo.genesis_prev_hash = DEFAULT_GENESIS_PREV_HASH
    block = _make_block(2, DEFAULT_GENESIS_PREV_HASH, "0" * 64)
    result = algo.validate_chain_link(block, None, DEFAULT_GENESIS_PREV_HASH)
    assert result.valid is False
    assert result.reason == "first block_index must be 1"


def test_validate_chain_link_rejects_non_one_first_index_direct_pos():
    # Given: PoS 合意実装と block_index=5 の先頭ブロック
    # When: validate_chain_link を直接呼ぶ
    # Then: first block_index must be 1 で失敗（base.py 側の検証を直接担保）
    algo = ProofOfStake(PosSettings())
    algo.genesis_prev_hash = DEFAULT_GENESIS_PREV_HASH
    block = {
        "block_index": 5,
        "block_header": {"prev_hash": DEFAULT_GENESIS_PREV_HASH},
    }
    result = algo.validate_chain_link(block, None, DEFAULT_GENESIS_PREV_HASH)
    assert result.valid is False
    assert result.reason == "first block_index must be 1"


def test_verify_chain_rejects_skipped_block_index():
    # Given: prev_hash は正しく連結されているが index がスキップされたチェーン
    # When: verify_chain_integrity を呼ぶ
    # Then: block_index mismatch で失敗（後続ブロック連続性の回帰ガード）
    first = _make_block(1, DEFAULT_GENESIS_PREV_HASH, "a" * 64)
    third = _make_block(3, first["block_header"]["tran_hash"], "b" * 64)
    result = verify_chain_integrity([first, third])
    assert result.valid is False
    assert result.reason == "block_index mismatch"
    assert result.failed_at_index == 2


def _find_nonce(prev_hash: str, body_hash: str, difficulty: int) -> int:
    nonce = 0
    while not meets_difficulty(
        calc_pow_tran_hash(prev_hash, body_hash, nonce), difficulty
    ):
        nonce += 1
    return nonce

def test_verify_chain_integrity_consensus_rejects_broken_link():
    # Given: consensus 指定で prev_hash が前ブロックの tran_hash と不一致なチェーン
    # When: verify_chain_integrity を呼ぶ
    # Then: 検証失敗
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=1))
    body = {"input_data": ["a"], "output_data": ["b"]}
    body_hash = calc_body_hash(body)
    chain = [
        _make_block(
            1, DEFAULT_GENESIS_PREV_HASH, calc_pow_tran_hash(DEFAULT_GENESIS_PREV_HASH, body_hash, 0)
        ),
        _make_block(2, "b" * 64, calc_pow_tran_hash("b" * 64, body_hash, 0)),
    ]
    result = verify_chain_integrity(chain, pow_algo, DEFAULT_GENESIS_PREV_HASH)
    assert result.valid is False
    assert result.failed_at_index == 2
    assert result.reason == "prev_hash mismatch"

def test_verify_chain_integrity_consensus_accepts_valid_chain():
    # Given: consensus 指定で prev_hash が整合な2ブロックの PoW チェーン
    # When: verify_chain_integrity を呼ぶ
    # Then: リンク検証に通って検証成功
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=1))
    pow_algo.genesis_prev_hash = DEFAULT_GENESIS_PREV_HASH
    body = {"input_data": ["a"], "output_data": ["b"]}
    body_hash = calc_body_hash(body)
    nonce1 = _find_nonce(DEFAULT_GENESIS_PREV_HASH, body_hash, 1)
    block1 = _make_block(
        1,
        DEFAULT_GENESIS_PREV_HASH,
        calc_pow_tran_hash(DEFAULT_GENESIS_PREV_HASH, body_hash, nonce1),
    )
    block1["block_header"]["nonce"] = nonce1
    nonce2 = _find_nonce(block1["block_header"]["tran_hash"], body_hash, 1)
    block2 = _make_block(
        2,
        block1["block_header"]["tran_hash"],
        calc_pow_tran_hash(block1["block_header"]["tran_hash"], body_hash, nonce2),
    )
    block2["block_header"]["nonce"] = nonce2
    result = verify_chain_integrity(
        [block1, block2], pow_algo, DEFAULT_GENESIS_PREV_HASH
    )
    assert result.valid is True
    assert result.failed_at_index is None


def test_verify_chain_valid_genesis_with_optional_consensus_type():
    # Given: 正しい genesis prev_hash を持つ先頭ブロック（legacy 形式）
    # When: verify_chain_integrity を呼ぶ
    # Then: 検証成功
    body = {"input_data": ["a"], "output_data": ["b"]}
    tran_hash = calc_legacy_tran_hash(DEFAULT_GENESIS_PREV_HASH, calc_body_hash(body))
    chain = [_make_block(1, DEFAULT_GENESIS_PREV_HASH, tran_hash, consensus_type=None)]
    result = verify_chain_integrity(chain)
    assert result.valid is True

def test_verify_chain_integrity_rejects_consensus_block_without_consensus():
    # Given: consensus 未指定かつ consensus_type 付きブロック
    # When: verify_chain_integrity を呼ぶ
    # Then: 内容検証がスキップされず失敗する
    chain = [_make_block(1, DEFAULT_GENESIS_PREV_HASH, "a" * 64)]
    result = verify_chain_integrity(chain)
    assert result.valid is False
    assert result.failed_at_index == 1
    assert result.reason == "consensus_type present but no consensus validator configured"

def test_verify_chain_integrity_rejects_protocol_mismatch():
    # Given: consensus=PoW 指定で consensus_type が異なるブロック
    # When: verify_chain_integrity を呼ぶ
    # Then: 内容検証がスキップされず失敗する
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=1))
    chain = [
        _make_block(1, DEFAULT_GENESIS_PREV_HASH, "a" * 64, consensus_type="pos")
    ]
    result = verify_chain_integrity(chain, pow_algo, DEFAULT_GENESIS_PREV_HASH)
    assert result.valid is False
    assert result.failed_at_index == 1
    assert result.reason == "consensus_type is not pow"


def test_verify_chain_integrity_pos_incremental_state_long_chain(pos_chain_setup):
    # Given: 報酬が蓄積する複数ブロックの PoS チェーン
    # When: verify_chain_integrity を呼ぶ
    # Then: インクリメンタル検証でも成功する（提案者選定は報酬後の状態に依存）
    from pos_helpers import build_pos_chain

    genesis_stakes, instances, settings = pos_chain_setup
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=5)
    pos = instances["validator-a"]
    result = verify_chain_integrity(
        chain, pos, DEFAULT_GENESIS_PREV_HASH, genesis_stakes=genesis_stakes
    )
    assert result.valid is True
    assert pos.validate_chain_with_genesis_stakes(chain, genesis_stakes) is True

def test_validate_chain_with_genesis_stakes_rejects_tampered_block(pos_chain_setup):
    # Given: 途中のブロックを改ざんした PoS チェーン
    # When: validate_chain_with_genesis_stakes を呼ぶ
    # Then: 失敗する
    from pos_helpers import build_pos_chain

    genesis_stakes, instances, settings = pos_chain_setup
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=3)
    chain[2]["tran_body"] = {"input_data": ["tampered"], "output_data": []}
    pos = instances["validator-a"]
    assert pos.validate_chain_with_genesis_stakes(chain, genesis_stakes) is False

def test_verify_chain_integrity_does_not_mutate_genesis_stakes(pos_chain_setup):
    # Given: genesis_stakes のコピーと検証可能な PoS チェーン
    # When: verify_chain_integrity / validate_chain_with_genesis_stakes を呼ぶ
    # Then: genesis_stakes 自体は検証後も変更されない
    from pos_helpers import build_pos_chain

    genesis_stakes, instances, settings = pos_chain_setup
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=3)
    pos = instances["validator-a"]
    snapshot = dict(genesis_stakes)
    assert (
        verify_chain_integrity(
            chain, pos, DEFAULT_GENESIS_PREV_HASH, genesis_stakes=genesis_stakes
        ).valid
        is True
    )
    assert genesis_stakes == snapshot
    assert pos.validate_chain_with_genesis_stakes(chain, genesis_stakes) is True
    assert genesis_stakes == snapshot
