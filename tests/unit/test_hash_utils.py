from useful_blockchain.hash_utils import genesis_hash
from useful_blockchain.types import DEFAULT_GENESIS_PREV_HASH


def test_genesis_hash_empty_chain():
    # Given: 空チェーンと設定 genesis
    # When: genesis_hash を呼ぶ
    # Then: 設定値が返る
    custom = "c" * 64
    assert genesis_hash([], custom) == custom


def test_genesis_hash_with_blocks():
    # Given: 先頭ブロックを持つチェーン
    # When: genesis_hash を呼ぶ
    # Then: 先頭ブロックの prev_hash が返る
    prev = "d" * 64
    chain = [
        {
            "block_index": 1,
            "block_header": {"prev_hash": prev, "tran_hash": "e" * 64},
            "tran_body": {"input_data": [], "output_data": []},
        }
    ]
    assert genesis_hash(chain, DEFAULT_GENESIS_PREV_HASH) == prev


def test_genesis_hash_missing_prev_hash_uses_fallback():
    # Given: prev_hash が欠落した先頭ブロック
    # When: genesis_hash を呼ぶ
    # Then: 引数の genesis_prev_hash がフォールバックとして使われる
    fallback = "f" * 64
    chain = [
        {
            "block_index": 1,
            "block_header": {"tran_hash": "e" * 64},
            "tran_body": {"input_data": [], "output_data": []},
        }
    ]
    assert genesis_hash(chain, fallback) == fallback
