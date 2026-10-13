import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from useful_blockchain.network.tls import (
    TlsConfigError,
    build_client_ssl_context,
    build_server_ssl_context,
    rejects_plain_websocket,
    url_scheme_matches_tls,
    validate_production_network,
    websocket_scheme,
)
from useful_blockchain.types import NetworkSettings, NodeSettings, TlsSettings


def _write_self_signed_cert(cert_path: Path, key_path: Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )


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


def test_build_server_ssl_context_returns_context_with_valid_cert_files(
    tmp_path: Path,
):
    # Given: 有効な証明書・鍵ファイルが存在する TLS 設定
    # When: build_server_ssl_context を呼ぶ
    # Then: SSLContext が返る
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    _write_self_signed_cert(cert, key)
    settings = TlsSettings(
        enabled=True,
        cert_file=str(cert),
        key_file=str(key),
    )
    context = build_server_ssl_context(settings)
    assert isinstance(context, ssl.SSLContext)


def test_build_server_ssl_context_rejects_invalid_pem(tmp_path: Path):
    # Given: 無効な PEM 内容の証明書・鍵ファイルが存在する TLS 設定
    # When: build_server_ssl_context を呼ぶ
    # Then: SSLError が発生する
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


def test_validate_production_network_skips_development():
    # Given: development 環境
    # When: validate_production_network を呼ぶ
    # Then: TLS 無効でも例外なし
    validate_production_network(
        NodeSettings(environment="development"),
        NetworkSettings(),
    )


def test_rejects_plain_websocket_tls_enabled():
    # Given: TLS 有効
    # When: rejects_plain_websocket を呼ぶ
    # Then: True
    assert rejects_plain_websocket(True, "development") is True
