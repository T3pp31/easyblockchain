"""load_yaml_config のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from useful_blockchain.settings import load_yaml_config


def test_load_yaml_config_returns_empty_dict_for_empty_document(
    tmp_path: Path,
) -> None:
    # Given: 空ファイルの YAML
    # When: load_yaml_config を呼ぶ
    # Then: 空の dict が返る
    config_path = tmp_path / "empty.yaml"
    config_path.write_text("# comment only\n", encoding="utf-8")
    assert load_yaml_config(config_path) == {}


def test_load_yaml_config_raises_when_top_level_is_list(
    tmp_path: Path,
) -> None:
    # Given: トップレベルがリストの YAML
    # When: load_yaml_config を呼ぶ
    # Then: ValueError が発生する
    config_path = tmp_path / "list.yaml"
    config_path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML mapping at the top level"):
        load_yaml_config(config_path)


def test_load_yaml_config_raises_when_top_level_is_scalar(
    tmp_path: Path,
) -> None:
    # Given: トップレベルがスカラーの YAML
    # When: load_yaml_config を呼ぶ
    # Then: ValueError が発生する
    config_path = tmp_path / "scalar.yaml"
    config_path.write_text("42\n", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML mapping at the top level"):
        load_yaml_config(config_path)


def test_load_yaml_config_returns_dict_for_mapping(tmp_path: Path) -> None:
    # Given: マッピング形式の YAML
    # When: load_yaml_config を呼ぶ
    # Then: dict が返る
    config_path = tmp_path / "valid.yaml"
    config_path.write_text("node:\n  log_level: INFO\n", encoding="utf-8")
    assert load_yaml_config(config_path) == {"node": {"log_level": "INFO"}}
