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


def test_meets_difficulty_rejects_difficulty_beyond_hash_length():
    # Given: 64 文字のハッシュとハッシュ長を超える difficulty
    # When: meets_difficulty を呼ぶ
    # Then: 不合格となり巨大文字列を生成しない
    from useful_blockchain.hash_utils import meets_difficulty

    assert not meets_difficulty("a" * 64, 65)
    assert not meets_difficulty("a" * 64, 10_000_000)
    assert meets_difficulty("0" * 64, 64)
    assert meets_difficulty("00" + "a" * 62, 2)
    assert not meets_difficulty("0" * 63 + "a", 64)
