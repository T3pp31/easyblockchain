import json
import hashlib

import pytest

from useful_blockchain.blockchain import BlockChain
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
