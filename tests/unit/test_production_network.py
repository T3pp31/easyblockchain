import pytest

from useful_blockchain.network.tls import (
    TlsConfigError,
    rejects_plain_websocket,
    validate_production_network,
)
from useful_blockchain.settings import parse_settings
from useful_blockchain.types import NetworkSettings, NodeSettings, TlsSettings


def _production_tls() -> dict[str, object]:
    return {
        "enabled": True,
        "cert_file": "/certs/server.crt",
        "key_file": "/certs/server.key",
        "ca_file": "/certs/ca.crt",
        "verify_peer": True,
    }


def test_parse_node_default_environment():
    # Given: environment 未指定
    # When: parse_settings を呼ぶ
    # Then: development がデフォルト
    settings = parse_settings({})
    assert settings.node.environment == "development"


def test_parse_node_production_environment():
    # Given: environment=production と本番 TLS 設定
    # When: parse_settings を呼ぶ
    # Then: パース成功
    settings = parse_settings(
        {
            "node": {"environment": "production"},
            "network": {"tls": _production_tls()},
        }
    )
    assert settings.node.environment == "production"
    assert settings.network.tls.enabled is True
    assert settings.network.tls.verify_peer is True


def test_parse_node_invalid_environment_raises():
    # Given: 不正な environment
    # When: parse_settings を呼ぶ
    # Then: ValueError
    with pytest.raises(ValueError, match="Unsupported environment"):
        parse_settings({"node": {"environment": "staging"}})


def test_production_requires_tls_enabled():
    # Given: production + tls.enabled=false
    # When: parse_settings を呼ぶ
    # Then: TlsConfigError
    with pytest.raises(TlsConfigError, match="tls.enabled=true"):
        parse_settings(
            {
                "node": {"environment": "production"},
                "network": {"tls": {"enabled": False, "verify_peer": False}},
            }
        )


def test_production_requires_verify_peer():
    # Given: production + verify_peer=false
    # When: parse_settings を呼ぶ
    # Then: TlsConfigError
    with pytest.raises(TlsConfigError, match="verify_peer=true"):
        parse_settings(
            {
                "node": {"environment": "production"},
                "network": {
                    "tls": {
                        "enabled": True,
                        "cert_file": "/certs/server.crt",
                        "key_file": "/certs/server.key",
                        "ca_file": "/certs/ca.crt",
                        "verify_peer": False,
                    }
                },
            }
        )


def test_production_requires_cert_paths():
    # Given: production + cert_file 未設定
    # When: parse_settings を呼ぶ
    # Then: TlsConfigError
    with pytest.raises(TlsConfigError, match="cert_file"):
        parse_settings(
            {
                "node": {"environment": "production"},
                "network": {
                    "tls": {
                        "enabled": True,
                        "cert_file": "",
                        "key_file": "/certs/server.key",
                        "ca_file": "/certs/ca.crt",
                        "verify_peer": True,
                    }
                },
            }
        )


def test_production_rejects_allow_private_ips():
    # Given: production + allow_private_ips=true
    # When: parse_settings を呼ぶ
    # Then: TlsConfigError
    with pytest.raises(TlsConfigError, match="allow_private_ips=false"):
        parse_settings(
            {
                "node": {"environment": "production"},
                "network": {
                    "peer_connect": {"allow_private_ips": True},
                    "tls": _production_tls(),
                },
            }
        )


def test_production_rejects_ws_bootstrap_peer():
    # Given: production + ws:// bootstrap
    # When: parse_settings を呼ぶ
    # Then: TlsConfigError
    with pytest.raises(TlsConfigError, match="wss:// bootstrap"):
        parse_settings(
            {
                "node": {"environment": "production"},
                "network": {
                    "bootstrap_peers": ["ws://127.0.0.1:8765"],
                    "tls": _production_tls(),
                },
            }
        )


def test_production_accepts_wss_bootstrap_peer():
    # Given: production + wss:// bootstrap
    # When: parse_settings を呼ぶ
    # Then: パース成功
    settings = parse_settings(
        {
            "node": {"environment": "production"},
            "network": {
                "bootstrap_peers": ["wss://127.0.0.1:8765"],
                "tls": _production_tls(),
            },
        }
    )
    assert settings.network.bootstrap_peers == ["wss://127.0.0.1:8765"]


def test_development_allows_tls_disabled():
    # Given: development + TLS 無効
    # When: validate_production_network を呼ぶ
    # Then: 例外なし
    validate_production_network(
        NodeSettings(environment="development"),
        NetworkSettings(tls=TlsSettings(enabled=False)),
    )


@pytest.mark.parametrize(
    "tls_enabled,environment,expected",
    [
        (False, "development", False),
        (True, "development", True),
        (False, "production", True),
        (True, "production", True),
    ],
)
def test_rejects_plain_websocket(tls_enabled: bool, environment: str, expected: bool):
    # Given: TLS 設定と environment
    # When: rejects_plain_websocket を呼ぶ
    # Then: 期待どおり平文拒否判定
    assert rejects_plain_websocket(tls_enabled, environment) is expected
