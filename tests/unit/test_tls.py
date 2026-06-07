import ssl
from pathlib import Path

import pytest

from useful_blockchain.network.tls import (
    TlsConfigError,
    build_client_ssl_context,
    build_server_ssl_context,
    url_scheme_matches_tls,
    websocket_scheme,
)
from useful_blockchain.types import TlsSettings


def test_websocket_scheme():
    # Given: TLS 有効/無効
    # When: websocket_scheme を呼ぶ
    # Then: ws または wss が返る
    assert websocket_scheme(False) == "ws"
    assert websocket_scheme(True) == "wss"


@pytest.mark.parametrize(
    "url,tls_enabled,expected",
    [
        ("ws://127.0.0.1:8765", False, True),
        ("ws://127.0.0.1:8765", True, False),
        ("wss://127.0.0.1:8765", False, True),
        ("wss://127.0.0.1:8765", True, True),
        ("http://127.0.0.1:8765", False, False),
    ],
)
def test_url_scheme_matches_tls(url: str, tls_enabled: bool, expected: bool):
    # Given: URL と TLS 設定
    # When: url_scheme_matches_tls を呼ぶ
    # Then: 期待どおりの整合性判定になる
    assert url_scheme_matches_tls(url, tls_enabled) is expected


def test_build_server_ssl_context_requires_cert_files(tmp_path: Path):
    # Given: 証明書ファイルが存在する TLS 設定
    # When: build_server_ssl_context を呼ぶ
    # Then: SSLContext が返る
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("dummy")
    key.write_text("dummy")
    settings = TlsSettings(
        enabled=True,
        cert_file=str(cert),
        key_file=str(key),
    )
    with pytest.raises(ssl.SSLError):
        build_server_ssl_context(settings)


def test_build_server_ssl_context_missing_files():
    # Given: 証明書パスが未設定
    # When: build_server_ssl_context を呼ぶ
    # Then: TlsConfigError が発生する
    settings = TlsSettings(enabled=True, cert_file="", key_file="")
    with pytest.raises(TlsConfigError, match="cert_file"):
        build_server_ssl_context(settings)


def test_build_client_ssl_context_without_verify():
    # Given: verify_peer=false
    # When: build_client_ssl_context を呼ぶ
    # Then: 検証無効の SSLContext が返る
    context = build_client_ssl_context(TlsSettings(verify_peer=False))
    assert context is not None
    assert context.verify_mode == ssl.CERT_NONE


def test_build_client_ssl_context_verify_requires_ca():
    # Given: verify_peer=true かつ ca_file 未設定
    # When: build_client_ssl_context を呼ぶ
    # Then: TlsConfigError が発生する
    with pytest.raises(TlsConfigError, match="ca_file"):
        build_client_ssl_context(TlsSettings(verify_peer=True, ca_file=""))
