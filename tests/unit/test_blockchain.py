import hashlib
import json

import pytest

from useful_blockchain.blockchain import BlockChain
from useful_blockchain.hash_utils import calc_body_hash, calc_legacy_tran_hash
from useful_blockchain.types import DEFAULT_GENESIS_PREV_HASH


def test_add_new_block(blockchain):
    block1 = blockchain.add_new_block("input1", "output1")
    block2 = blockchain.add_new_block("input2", "output2")
    assert len(blockchain.chain) == 2
    assert block1["block_index"] == 1
    assert block2["block_index"] == 2


def test_calc_tran_hash(blockchain):
    input_data = "test_input"
    output_data = "test_output"
    new_transaction = blockchain._BlockChain__create_new_transaction(input_data, output_data)
    calculated_hash = blockchain._BlockChain__calc_tran_hash(new_transaction)
    tran_string = json.dumps(new_transaction, sort_keys=True).encode()
    expected_hash = hashlib.sha256(str(tran_string).encode()).hexdigest()
    assert calculated_hash == expected_hash


def test_dump_entire_chain(capsys, blockchain):
    blockchain.add_new_block(["input1"], ["output1"])
    blockchain.dump(0)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert len(parsed) == 1
    assert parsed[0]["block_index"] == 1


def test_dump_single_block(capsys, blockchain):
    blockchain.add_new_block(["a"], ["b"])
    blockchain.add_new_block(["c"], ["d"])
    blockchain.dump(1)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["block_index"] == 1


def test_dump_invalid_block_index(capsys, blockchain):
    blockchain.dump(99)
    captured = capsys.readouterr()
    assert "無効なブロックインデックスです。" in captured.out


def test_add_block_without_key_when_signature_enabled():
    bc = BlockChain(enable_signature=True)
    with pytest.raises(ValueError, match="秘密鍵が設定されていません"):
        bc.add_new_block(["a"], ["b"])


def test_first_block_uses_fixed_genesis_prev_hash(blockchain):
    # Given: デフォルト BlockChain
    # When: 先頭ブロックを追加
    # Then: prev_hash が固定 genesis 値と一致
    block = blockchain.add_new_block(["a"], ["b"])
    assert block["block_header"]["prev_hash"] == DEFAULT_GENESIS_PREV_HASH


def test_first_block_custom_genesis_prev_hash():
    # Given: カスタム genesis prev_hash を指定した BlockChain
    # When: 先頭ブロックを追加
    # Then: 指定値が prev_hash になる
    custom = "1" * 64
    bc = BlockChain(genesis_prev_hash=custom)
    block = bc.add_new_block(["a"], ["b"])
    assert block["block_header"]["prev_hash"] == custom


def test_verify_chain_legacy(blockchain):
    blockchain.add_new_block(["a"], ["b"])
    blockchain.add_new_block(["c"], ["d"])
    result = blockchain.verify_chain()
    assert result.valid is True


def test_replace_chain_syncs_pos_validators(pos_setup):
    # Given: 検証可能な PoS チェーンと genesis_stakes
    # When: replace_chain を genesis_stakes 付きで呼ぶ
    # Then: バリデータのステークがチェーンに応じて更新される
    from pos_helpers import build_pos_chain

    from useful_blockchain.consensus.pos import ProofOfStake

    validators, _, instances, settings = pos_setup
    genesis_stakes = dict(validators)
    new_chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=1)

    pos = ProofOfStake(settings, node_validator_id="validator-a")
    for vid, stake in genesis_stakes.items():
        pos.register_validator(
            vid, stake, managers[vid].export_public_key().decode("utf-8")
        )

    bc = BlockChain(enable_signature=True, consensus=pos)
    proposer = new_chain[0]["block_header"]["validator_id"]

    assert bc.replace_chain(new_chain, genesis_stakes=genesis_stakes) is True
    assert pos.validators[proposer] == genesis_stakes[proposer] + settings.block_reward


def test_replace_chain_syncs_multi_block_pos_validators(pos_setup):
    # Given: 複数ブロックの PoS チェーン
    # When: replace_chain を genesis_stakes 付きで呼ぶ
    # Then: 全バリデータのステークが再生結果と一致
    from pos_helpers import build_pos_chain

    from useful_blockchain.consensus.pos import ProofOfStake

    validators, _, instances, settings = pos_setup
    genesis_stakes = dict(validators)
    new_chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=3)

    pos = ProofOfStake(settings, node_validator_id="validator-a")
    for vid, stake in genesis_stakes.items():
        pos.register_validator(
            vid, stake, managers[vid].export_public_key().decode("utf-8")
        )

    bc = BlockChain(enable_signature=True, consensus=pos)
    assert bc.replace_chain(new_chain, genesis_stakes=genesis_stakes) is True
    expected = ProofOfStake.compute_validators_from_chain(
        new_chain, genesis_stakes, settings
    )
    assert pos.validators == expected


def test_replace_chain_rejects_invalid_chain_and_preserves_stakes(pos_setup):
    # Given: 不正 proposer を含むチェーン
    # When: replace_chain を呼ぶ
    # Then: False を返しステークは変わらない
    from pos_helpers import build_pos_chain

    from useful_blockchain.consensus.pos import ProofOfStake

    validators, _, instances, settings = pos_setup
    genesis_stakes = dict(validators)
    chain = build_pos_chain(genesis_stakes, instances, settings, num_blocks=1)
    actual_proposer = chain[0]["block_header"]["validator_id"]
    wrong_proposer = (
        "validator-b" if actual_proposer == "validator-a" else "validator-a"
    )
    bad_chain = [dict(chain[0])]
    bad_chain[0]["block_header"] = dict(chain[0]["block_header"])
    bad_chain[0]["block_header"]["validator_id"] = wrong_proposer

    pos = ProofOfStake(settings, node_validator_id="validator-a")
    for vid, stake in genesis_stakes.items():
        pos.register_validator(vid, stake)
    original_stakes = dict(pos.validators)

    bc = BlockChain(enable_signature=True, consensus=pos)
    assert bc.replace_chain(bad_chain, genesis_stakes=genesis_stakes) is False
    assert pos.validators == original_stakes
    assert bc.chain == []


def test_replace_chain_empty_chain_resets_to_genesis_stakes(pos_setup):
    # Given: ステークが増加済みの PoS
    # When: 空チェーンで replace_chain
    # Then: stakes は genesis_stakes に戻る
    from useful_blockchain.consensus.pos import ProofOfStake

    validators, _, _, settings = pos_setup
    genesis_stakes = dict(validators)

    pos = ProofOfStake(settings, node_validator_id="validator-a")
    for vid, stake in genesis_stakes.items():
        pos.register_validator(vid, stake)
    pos.validators["validator-a"] += settings.block_reward

    bc = BlockChain(enable_signature=True, consensus=pos)
    assert bc.replace_chain([], genesis_stakes=genesis_stakes) is True
    assert pos.validators == genesis_stakes


def _legacy_block(index: int, prev_hash: str, tran_hash: str) -> dict:
    return {
        "block_index": index,
        "block_item": "2026-01-01 00:00:00",
        "block_header": {"prev_hash": prev_hash, "tran_hash": tran_hash},
        "tran_counter": 1,
        "tran_body": {"input_data": ["a"], "output_data": ["b"]},
    }


def test_add_block_rejects_wrong_prev_hash_legacy(blockchain):
    # Given: 既存チェーンと prev_hash が不正なブロック
    # When: add_block を呼ぶ
    # Then: False を返す
    first = blockchain.add_new_block(["a"], ["b"])
    bad = _legacy_block(2, "f" * 64, first["block_header"]["tran_hash"])
    assert blockchain.add_block(bad, validate=True) is False


def test_add_block_rejects_bad_block_index_legacy(blockchain):
    # Given: block_index が連続しないブロック
    # When: add_block を呼ぶ
    # Then: False を返す
    first = blockchain.add_new_block(["a"], ["b"])
    bad = _legacy_block(3, first["block_header"]["tran_hash"], "a" * 64)
    assert blockchain.add_block(bad, validate=True) is False


def test_add_block_rejects_bad_legacy_tran_hash(blockchain):
    # Given: レガシー tran_hash が不一致のブロック
    # When: add_block を呼ぶ
    # Then: False を返す
    first = blockchain.add_new_block(["a"], ["b"])
    bad = _legacy_block(2, first["block_header"]["tran_hash"], "a" * 64)
    assert blockchain.add_block(bad, validate=True) is False


def test_add_block_rejects_wrong_genesis_prev_hash_on_empty_chain(blockchain):
    # Given: 空チェーンと genesis prev_hash が不一致のブロック
    # When: add_block を呼ぶ
    # Then: False を返す
    bad = _legacy_block(1, "f" * 64, "a" * 64)
    assert blockchain.add_block(bad, validate=True) is False


def test_add_block_accepts_valid_legacy_block(blockchain):
    # Given: 正しいレガシーブロック
    # When: add_block を呼ぶ
    # Then: True を返しチェーンに追加される
    first = blockchain.add_new_block(["a"], ["b"])
    body_hash = calc_body_hash({"input_data": ["a"], "output_data": ["b"]})
    tran_hash = calc_legacy_tran_hash(first["block_header"]["tran_hash"], body_hash)
    valid = _legacy_block(2, first["block_header"]["tran_hash"], tran_hash)
    assert blockchain.add_block(valid, validate=True) is True
    assert len(blockchain.chain) == 2


def test_add_block_does_not_revalidate_existing_chain(pow_blockchain):
    # Given: 既存ブロックを破損させた PoW チェーン
    # When: 正しく採掘された次ブロックを add_block で追加する
    # Then: 既存チェーンの再検証は行われず追加に成功する
    pow_blockchain.add_new_block(["a"], ["b"])
    pow_blockchain.chain[0]["block_header"]["tran_hash"] = "f" * 64

    candidate = {
        "block_index": 2,
        "block_item": "2026-01-01 00:00:00",
        "block_header": {
            "prev_hash": pow_blockchain.chain[-1]["block_header"]["tran_hash"],
            "tran_hash": "",
            "consensus_type": "pow",
        },
        "tran_body": {"input_data": ["x"], "output_data": ["y"]},
    }
    mined = pow_blockchain.consensus.prepare_block(candidate, pow_blockchain.chain)
    assert pow_blockchain.add_block(mined, validate=True) is True


def test_add_block_rejects_invalid_consensus_block(pow_blockchain):
    # Given: tran_hash が不正な PoW ブロック
    # When: add_block を呼ぶ
    # Then: False を返す
    pow_blockchain.add_new_block(["a"], ["b"])
    bad = {
        "block_index": 2,
        "block_item": "2026-01-01 00:00:00",
        "block_header": {
            "prev_hash": pow_blockchain.chain[-1]["block_header"]["tran_hash"],
            "tran_hash": "a" * 64,
            "consensus_type": "pow",
            "nonce": 0,
            "difficulty": 1,
        },
        "tran_body": {"input_data": ["x"], "output_data": ["y"]},
    }
    assert pow_blockchain.add_block(bad, validate=True) is False


def test_add_block_rejects_wrong_first_block_index_on_empty_chain(blockchain):
    # Given: 空チェーンと block_index が 1 でないブロック
    # When: add_block を呼ぶ
    # Then: False を返す
    for bad_index in (0, -1, 99):
        bad = _legacy_block(bad_index, DEFAULT_GENESIS_PREV_HASH, "a" * 64)
        assert blockchain.add_block(bad, validate=True) is False
    assert blockchain.chain == []


def test_add_block_rejects_missing_block_index(blockchain):
    # Given: block_index を欠くブロック
    # When: add_block を呼ぶ
    # Then: 例外ではなく False を返す
    first = blockchain.add_new_block(["a"], ["b"])
    bad = _legacy_block(2, first["block_header"]["tran_hash"], "a" * 64)
    del bad["block_index"]
    assert blockchain.add_block(bad, validate=True) is False


def test_add_block_rejects_missing_tran_body(blockchain):
    # Given: tran_body を欠くブロック
    # When: add_block を呼ぶ
    # Then: 例外ではなく False を返す
    first = blockchain.add_new_block(["a"], ["b"])
    bad = _legacy_block(2, first["block_header"]["tran_hash"], "a" * 64)
    del bad["tran_body"]
    assert blockchain.add_block(bad, validate=True) is False


def test_add_new_block_tran_hash_matches_legacy_formula(blockchain):
    # Given: consensus なしの BlockChain
    # When: add_new_block で生成したブロックの tran_hash を検証
    # Then: calc_legacy_tran_hash(prev_hash, calc_body_hash(tran_body)) と一致する
    block = blockchain.add_new_block(["a"], ["b"])
    body_hash = calc_body_hash(block["tran_body"])
    expected = calc_legacy_tran_hash(DEFAULT_GENESIS_PREV_HASH, body_hash)
    assert block["block_header"]["tran_hash"] == expected

    second = blockchain.add_new_block(["c"], ["d"])
    second_body_hash = calc_body_hash(second["tran_body"])
    second_expected = calc_legacy_tran_hash(
        block["block_header"]["tran_hash"], second_body_hash
    )
    assert second["block_header"]["tran_hash"] == second_expected
