import pytest

from useful_blockchain.settings import parse_settings


def test_parse_observability_defaults():
    # Given: observability セクションなし
    # When: parse_settings を呼ぶ
    # Then: デフォルト値が設定される
    settings = parse_settings({})
    assert settings.observability.enabled is False
    assert settings.observability.port == 9090
    assert settings.observability.log_format == "text"


def test_parse_observability_custom_values():
    # Given: observability 設定
    # When: parse_settings を呼ぶ
    # Then: 値が反映される
    settings = parse_settings(
        {
            "observability": {
                "enabled": True,
                "port": 9100,
                "log_format": "json",
                "min_peers_for_ready": 1,
            }
        }
    )
    assert settings.observability.enabled is True
    assert settings.observability.port == 9100
    assert settings.observability.log_format == "json"
    assert settings.observability.min_peers_for_ready == 1


def test_parse_observability_invalid_log_format():
    # Given: 不正な log_format
    # When: parse_settings を呼ぶ
    # Then: ValueError が発生する
    with pytest.raises(ValueError, match="Unsupported log format"):
        parse_settings({"observability": {"log_format": "xml"}})
