"""WebSocket TLS (WSS) 用 SSL コンテキスト構築。"""

from __future__ import annotations

import ssl
from pathlib import Path

from useful_blockchain.types import Environment, NetworkSettings, NodeSettings, TlsSettings


class TlsConfigError(ValueError):
    """TLS 設定が不正な場合の例外。"""


def _validate_cert_paths(settings: TlsSettings) -> None:
    if not settings.cert_file or not settings.key_file:
        raise TlsConfigError("tls.enabled requires cert_file and key_file")
    cert_path = Path(settings.cert_file)
    key_path = Path(settings.key_file)
    if not cert_path.is_file():
        raise TlsConfigError(f"TLS cert file not found: {cert_path}")
    if not key_path.is_file():
        raise TlsConfigError(f"TLS key file not found: {key_path}")


def build_server_ssl_context(settings: TlsSettings) -> ssl.SSLContext:
    """サーバー用 SSL コンテキストを構築する。"""
    if not settings.enabled:
        raise TlsConfigError("TLS is not enabled")
    _validate_cert_paths(settings)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(settings.cert_file, settings.key_file)
    return context


def build_client_ssl_context(settings: TlsSettings) -> ssl.SSLContext | None:
    """クライアント用 SSL コンテキストを構築する。検証無効時は None を返す。"""
    if not settings.verify_peer:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    if not settings.ca_file:
        raise TlsConfigError("tls.verify_peer requires ca_file")
    ca_path = Path(settings.ca_file)
    if not ca_path.is_file():
        raise TlsConfigError(f"TLS CA file not found: {ca_path}")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(settings.ca_file)
    return context


def websocket_scheme(tls_enabled: bool) -> str:
    """TLS 有効時の WebSocket スキームを返す。"""
    return "wss" if tls_enabled else "ws"


def url_scheme_matches_tls(url: str, tls_enabled: bool) -> bool:
    """URL スキームと TLS 設定の整合性を検証する。"""
    if url.startswith("wss://"):
        return True
    if url.startswith("ws://"):
        return not tls_enabled
    return False


def rejects_plain_websocket(tls_enabled: bool, environment: Environment) -> bool:
    """平文 WebSocket 接続を拒否すべきかどうかを返す。"""
    return tls_enabled or environment == "production"


def validate_production_network(node: NodeSettings, network: NetworkSettings) -> None:
    """本番環境向けのネットワーク/TLS 設定を検証する。"""
    if node.environment != "production":
        return

    tls = network.tls
    if not tls.enabled:
        raise TlsConfigError("production environment requires network.tls.enabled=true")
    if not tls.verify_peer:
        raise TlsConfigError("production environment requires network.tls.verify_peer=true")
    if not tls.cert_file:
        raise TlsConfigError("production environment requires network.tls.cert_file")
    if not tls.key_file:
        raise TlsConfigError("production environment requires network.tls.key_file")
    if not tls.ca_file:
        raise TlsConfigError("production environment requires network.tls.ca_file")

    for url in network.bootstrap_peers:
        if not url_scheme_matches_tls(url, tls_enabled=True):
            raise TlsConfigError(
                f"production environment requires wss:// bootstrap peers, got: {url!r}"
            )
