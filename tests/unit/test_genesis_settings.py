import pytest

from useful_blockchain.settings import _parse_genesis, parse_settings
from useful_blockchain.types import DEFAULT_GENESIS_PREV_HASH


def test_parse_genesis_default():
    # Given: 空の genesis 設定
    # When: _parse_genesis を呼ぶ
    # Then: デフォルトの prev_hash が返る
    settings = _parse_genesis({})
    assert settings.prev_hash == DEFAULT_GENESIS_PREV_HASH


def test_parse_genesis_valid_hex():
    # Given: 有効な64文字 hex
    # When: _parse_genesis を呼ぶ
    # Then: 小文字に正規化された値が返る
    custom = "a" * 64
    settings = _parse_genesis({"prev_hash": custom.upper()})
    assert settings.prev_hash == custom


@pytest.mark.parametrize(
    "prev_hash,match",
    [
        ("abc", "64-character"),
        ("g" * 64, "64-character"),
        ("0" * 63, "64-character"),
        ("0" * 65, "64-character"),
    ],
)
def test_parse_genesis_invalid(prev_hash: str, match: str):
    # Given: 不正な prev_hash
    # When: _parse_genesis を呼ぶ
    # Then: ValueError が発生する
    with pytest.raises(ValueError, match=match):
        _parse_genesis({"prev_hash": prev_hash})


def test_parse_settings_includes_genesis():
    # Given: genesis セクション付き設定
    # When: parse_settings を呼ぶ
    # Then: AppSettings.genesis が設定される
    settings = parse_settings({"genesis": {"prev_hash": "b" * 64}})
    assert settings.genesis.prev_hash == "b" * 64
