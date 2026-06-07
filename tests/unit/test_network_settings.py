import logging

import pytest

from useful_blockchain.settings import (
    _parse_network,
    _parse_node,
    parse_settings,
    resolve_log_level,
)


def test_parse_network_defaults():
    # Given: 空の network 設定
    # When: _parse_network を呼ぶ
    # Then: 既存デフォルトと新規タイムアウトのデフォルトが返る
    settings = _parse_network({})
    assert settings.connection_timeout_seconds == 10
    assert settings.chain_sync_timeout_seconds == 10
    assert settings.shutdown_peer_close_timeout_seconds == 2
    assert settings.shutdown_server_wait_timeout_seconds == 3
    assert settings.pong_timeout_seconds == 90
    assert settings.tls.enabled is False
    assert settings.peer_auth.enabled is True
    assert settings.rate_limit.max_connections_per_ip_per_minute == 10
    assert settings.reconnect.enabled is True
    assert settings.chain_sync_batch_size == 100
    assert settings.transport == "websocket"
    assert settings.libp2p.gossipsub_mesh_n == 6


def test_parse_network_custom_values():
    # Given: カスタム network 設定
    # When: _parse_network を呼ぶ
    # Then: 指定値が読み込まれる
    settings = _parse_network(
        {
            "chain_sync_timeout_seconds": 30,
            "shutdown_peer_close_timeout_seconds": 5,
            "shutdown_server_wait_timeout_seconds": 7,
        }
    )
    assert settings.chain_sync_timeout_seconds == 30
    assert settings.shutdown_peer_close_timeout_seconds == 5
    assert settings.shutdown_server_wait_timeout_seconds == 7


def test_parse_network_chain_sync_timeout_zero():
    # Given: chain_sync_timeout_seconds が 0
    # When: _parse_network を呼ぶ
    # Then: 0 が許容される
    settings = _parse_network({"chain_sync_timeout_seconds": 0})
    assert settings.chain_sync_timeout_seconds == 0


def test_parse_node_default_log_level():
    # Given: 空の node 設定
    # When: _parse_node を呼ぶ
    # Then: log_level のデフォルトは INFO
    settings = _parse_node({})
    assert settings.log_level == "INFO"


def test_parse_node_custom_log_level():
    # Given: カスタム log_level
    # When: _parse_node を呼ぶ
    # Then: 指定値が保持される
    settings = _parse_node({"log_level": "WARNING"})
    assert settings.log_level == "WARNING"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("DEBUG", logging.DEBUG),
        ("debug", logging.DEBUG),
        ("INFO", logging.INFO),
        ("info", logging.INFO),
        ("WARNING", logging.WARNING),
        ("ERROR", logging.ERROR),
        ("CRITICAL", logging.CRITICAL),
        ("  info  ", logging.INFO),
    ],
)
def test_resolve_log_level_valid(name: str, expected: int):
    # Given: 有効なログレベル名
    # When: resolve_log_level を呼ぶ
    # Then: 対応する logging 定数が返る
    assert resolve_log_level(name) == expected


@pytest.mark.parametrize(
    "name",
    ["TRACE", "NOTSET", "VERBOSE", "", "infoo"],
)
def test_resolve_log_level_invalid(name: str):
    # Given: 不正なログレベル名
    # When: resolve_log_level を呼ぶ
    # Then: ValueError が発生する
    with pytest.raises(ValueError, match="Unsupported log level"):
        resolve_log_level(name)


def test_parse_node_invalid_log_level():
    # Given: 不正な log_level
    # When: _parse_node を呼ぶ
    # Then: ValueError が発生する
    with pytest.raises(ValueError, match="Unsupported log level"):
        _parse_node({"log_level": "INVALID"})


def test_parse_settings_includes_new_network_and_node_fields():
    # Given: 新規キーを含む設定
    # When: parse_settings を呼ぶ
    # Then: AppSettings に反映される
    settings = parse_settings(
        {
            "network": {
                "chain_sync_timeout_seconds": 15,
                "shutdown_peer_close_timeout_seconds": 4,
                "shutdown_server_wait_timeout_seconds": 6,
            },
            "node": {"log_level": "DEBUG"},
        }
    )
    assert settings.network.chain_sync_timeout_seconds == 15
    assert settings.network.shutdown_peer_close_timeout_seconds == 4
    assert settings.network.shutdown_server_wait_timeout_seconds == 6
    assert settings.node.log_level == "DEBUG"
