"""真偽値設定のパースに関するテスト。"""

from __future__ import annotations

import pytest

from useful_blockchain.settings import _parse_network, parse_settings


def test_parse_network_treats_quoted_false_as_false() -> None:
    # Given: allow_private_ips に引用符付き文字列 "false"
    # When: _parse_network を呼ぶ
    # Then: False として解釈される
    settings = _parse_network({"peer_connect": {"allow_private_ips": "false"}})
    assert settings.peer_connect.allow_private_ips is False


def test_parse_network_treats_quoted_true_as_true() -> None:
    # Given: tls.enabled に引用符付き文字列 "true"
    # When: _parse_network を呼ぶ
    # Then: True として解釈される
    settings = _parse_network({"tls": {"enabled": "true"}})
    assert settings.tls.enabled is True


def test_parse_bool_is_case_insensitive() -> None:
    # Given: 大文字混在の文字列真偽値
    # When: parse_settings を呼ぶ
    # Then: 大小非依存で解釈される
    settings = parse_settings({"persistence": {"store_keys_on_disk": "False"}})
    assert settings.persistence.store_keys_on_disk is False


def test_parse_settings_rejects_invalid_bool_string() -> None:
    # Given: true/false 以外の文字列
    # When: parse_settings を呼ぶ
    # Then: ValueError が発生する
    with pytest.raises(ValueError, match="persistence.store_keys_on_disk must be a boolean"):
        parse_settings({"persistence": {"store_keys_on_disk": "yes"}})


def test_parse_settings_rejects_non_bool_scalar() -> None:
    # Given: 真偽値以外のスカラー（整数）
    # When: parse_settings を呼ぶ
    # Then: ValueError が発生する
    with pytest.raises(ValueError, match="node.require_external_keys must be a boolean"):
        parse_settings({"node": {"require_external_keys": 1}})


def test_parse_bool_uses_default_when_null() -> None:
    # Given: 真偽値フィールドが null
    # When: parse_settings を呼ぶ
    # Then: デフォルト値が採用される
    settings = parse_settings({"network": {"peer_auth": {"enabled": None}}})
    assert settings.network.peer_auth.enabled is True


def test_parse_bool_accepts_real_bools() -> None:
    # Given: 真偽値リテラル
    # When: parse_settings を呼ぶ
    # Then: そのまま解釈される
    settings = parse_settings(
        {"node": {"require_external_keys": True}, "persistence": {"store_keys_on_disk": False}}
    )
    assert settings.node.require_external_keys is True
    assert settings.persistence.store_keys_on_disk is False
