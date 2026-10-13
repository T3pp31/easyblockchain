"""null 設定セクションの扱いに関するテスト。"""

from __future__ import annotations

import pytest

from useful_blockchain.settings import _parse_network, parse_settings


def test_parse_settings_treats_null_sections_as_empty() -> None:
    # Given: 全セクションが null の設定
    # When: parse_settings を呼ぶ
    # Then: AttributeError にならずデフォルトで成功する
    data = {
        "network": None,
        "node": None,
        "consensus": None,
        "genesis": None,
        "persistence": None,
        "observability": None,
    }
    settings = parse_settings(data)
    assert settings.node.environment == "development"
    assert settings.consensus.type == "pow"


def test_parse_network_treats_null_subsections_as_empty() -> None:
    # Given: network のサブセクションが null
    # When: _parse_network を呼ぶ
    # Then: AttributeError にならずデフォルトで成功する
    data = {
        "tls": None,
        "peer_auth": None,
        "peer_connect": None,
        "rate_limit": None,
        "reconnect": None,
    }
    settings = _parse_network(data)
    assert settings.tls.enabled is False
    assert settings.peer_auth.enabled is True
    assert settings.reconnect.enabled is True


def test_parse_consensus_treats_null_pow_pos_as_empty() -> None:
    # Given: consensus.pow / consensus.pos が null
    # When: parse_settings を呼ぶ
    # Then: AttributeError にならずデフォルトで成功する
    settings = parse_settings({"consensus": {"type": "pos", "pow": None, "pos": None}})
    assert settings.consensus.pow.initial_difficulty == 4
    assert settings.consensus.pos.min_stake == 100


def test_parse_settings_rejects_non_dict_section() -> None:
    # Given: network が dict 以外
    # When: parse_settings を呼ぶ
    # Then: ValueError が発生する
    with pytest.raises(ValueError, match="network must be a mapping"):
        parse_settings({"network": "invalid"})


def test_parse_node_uses_default_data_dir_when_null() -> None:
    # Given: data_dir が null
    # When: parse_settings を呼ぶ
    # Then: "./None" ではなくデフォルトの data_dir になる
    settings = parse_settings({"node": {"data_dir": None}})
    assert not settings.node.data_dir.endswith("None")
    assert settings.node.data_dir.endswith("data")
