from unittest.mock import MagicMock

from useful_blockchain.network.discovery import PeerDiscovery, _mdns_tls_enabled
from useful_blockchain.types import NetworkSettings, TlsSettings


def test_mdns_tls_enabled_reads_txt_flag() -> None:
    # Given: TXT レコードに tls=1 が含まれる
    # When: フラグを解釈する
    # Then: TLS 有効と判定される
    assert _mdns_tls_enabled({b"tls": b"1"}) is True


def test_mdns_tls_enabled_false_when_flag_absent() -> None:
    # Given: TXT レコードに tls フラグがない
    # When: フラグを解釈する
    # Then: TLS 無効と判定される
    assert _mdns_tls_enabled(None) is False
    assert _mdns_tls_enabled({}) is False
    assert _mdns_tls_enabled({b"tls": b"0"}) is False


def test_register_self_advertises_tls_flag(tmp_path=None) -> None:
    # Given: TLS 有効な設定
    # When: _register_self を呼ぶ
    # Then: TXT に tls=1 を持つ ServiceInfo が登録される
    discovery = PeerDiscovery(
        NetworkSettings(tls=TlsSettings(enabled=True)),
        "wss://127.0.0.1:8765",
        "development",
    )
    zc = MagicMock()
    discovery._register_self(zc)
    info = zc.register_service.call_args[0][0]
    assert info.properties == {b"tls": b"1"}
    assert info.port == 8765


def test_register_self_advertises_tls_disabled(tmp_path=None) -> None:
    # Given: TLS 無効な設定
    # When: _register_self を呼ぶ
    # Then: TXT に tls=0 が登録される
    discovery = PeerDiscovery(
        NetworkSettings(), "ws://127.0.0.1:8765", "development"
    )
    zc = MagicMock()
    discovery._register_self(zc)
    info = zc.register_service.call_args[0][0]
    assert info.properties == {b"tls": b"0"}
