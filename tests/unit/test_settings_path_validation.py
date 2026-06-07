"""設定パース時のパス検証テスト。"""

from __future__ import annotations

import pytest

from useful_blockchain.settings import parse_settings


def test_parse_settings_rejects_traversal_in_chain_file() -> None:
    # Given: chain_file にパストラバーサル
    # When: parse_settings を呼ぶ
    # Then: ValueError が発生する
    with pytest.raises(ValueError, match="persistence.chain_file"):
        parse_settings({"persistence": {"chain_file": "../../escape.json"}})


def test_parse_settings_rejects_traversal_in_keys_dir() -> None:
    # Given: keys_dir にパストラバーサル
    # When: parse_settings を呼ぶ
    # Then: ValueError が発生する
    with pytest.raises(ValueError, match="persistence.keys_dir"):
        parse_settings({"persistence": {"keys_dir": "../keys"}})


def test_parse_settings_normalizes_data_dir(tmp_path) -> None:
    # Given: 相対パスの data_dir
    # When: parse_settings を呼ぶ
    # Then: 絶対パスに正規化される
    settings = parse_settings({"node": {"data_dir": str(tmp_path / "relative-data")}})
    assert settings.node.data_dir == str((tmp_path / "relative-data").resolve())
