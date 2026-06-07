"""ピア URL 検証のユニットテスト。"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from useful_blockchain.network.discovery import PeerDiscovery
from useful_blockchain.network.peer import connect_to_peer
from useful_blockchain.network.peer_url import (
    PeerConnectTarget,
    resolve_peer_connect_target,
    validate_peer_url,
)
from useful_blockchain.types import NetworkSettings, PeerConnectSettings


def _network(**peer_connect_kwargs: object) -> NetworkSettings:
    return NetworkSettings(
        peer_connect=PeerConnectSettings(**peer_connect_kwargs),
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("ws://127.0.0.1:8765", None),
        ("ws://10.0.0.1:8765", None),
        ("ws://192.168.1.10:8765", None),
        ("ws://169.254.169.254:80", None),
        ("http://8.8.8.8:8765", None),
        ("ws://8.8.8.8:8765/extra", None),
        ("ws://user@8.8.8.8:8765", None),
    ],
)
def test_validate_peer_url_rejects_restricted_or_invalid_urls(
    url: str, expected: None
) -> None:
    # Given: 制限対象または不正な URL
    # When: validate_peer_url を呼ぶ
    # Then: None が返る
    assert validate_peer_url(url, _network(), "development") is expected


def test_validate_peer_url_allows_public_ip() -> None:
    # Given: 公開 IP の WebSocket URL
    # When: validate_peer_url を呼ぶ
    # Then: URL が返る
    url = "ws://8.8.8.8:8765"
    assert validate_peer_url(url, _network(), "development") == url


def test_validate_peer_url_allows_private_ip_when_enabled() -> None:
    # Given: allow_private_ips=true
    # When: ループバック URL を検証する
    # Then: URL が返る
    url = "ws://127.0.0.1:8765"
    settings = _network(allow_private_ips=True)
    assert validate_peer_url(url, settings, "development") == url


def test_validate_peer_url_blocks_metadata_ip_even_when_private_allowed() -> None:
    # Given: allow_private_ips=true でもメタデータ IP は拒否
    # When: メタデータ URL を検証する
    # Then: None が返る
    url = "ws://169.254.169.254:80"
    settings = _network(allow_private_ips=True)
    assert validate_peer_url(url, settings, "development") is None


def test_discovery_add_peer_skips_restricted_url() -> None:
    # Given: プライベート IP を拒否する discovery
    # When: 内部 URL を add_peer する
    # Then: known_peers に追加されない
    discovery = PeerDiscovery(_network(), "ws://127.0.0.1:9000", "development")
    discovery.add_peer("ws://127.0.0.1:8765")
    assert discovery.known_peers == []


def test_discovery_add_peers_truncates_message() -> None:
    # Given: max_peers_per_message=2
    # When: 3 件の URL を add_peers する
    # Then: 先頭 2 件のみ処理される
    settings = NetworkSettings(
        peer_connect=PeerConnectSettings(
            allow_private_ips=True,
            max_peers_per_message=2,
        )
    )
    discovery = PeerDiscovery(settings, "ws://127.0.0.1:9000", "development")
    discovery.add_peers(
        [
            "ws://127.0.0.1:8765",
            "ws://127.0.0.1:8766",
            "ws://127.0.0.1:8767",
        ]
    )
    assert discovery.known_peers == [
        "ws://127.0.0.1:8765",
        "ws://127.0.0.1:8766",
    ]


def test_resolve_peer_connect_target_pins_literal_public_ip() -> None:
    # Given: 公開 IP のリテラル URL
    # When: resolve_peer_connect_target を呼ぶ
    # Then: ピンされた接続先が返る
    url = "ws://8.8.8.8:8765"
    target = resolve_peer_connect_target(url, _network(), "development")
    assert target == PeerConnectTarget(
        url=url,
        host="8.8.8.8",
        port=8765,
        hostname="8.8.8.8",
    )


def test_resolve_peer_connect_target_rejects_restricted_ip() -> None:
    # Given: ループバック IP の URL
    # When: resolve_peer_connect_target を呼ぶ
    # Then: None が返る
    assert (
        resolve_peer_connect_target("ws://127.0.0.1:8765", _network(), "development")
        is None
    )


def test_resolve_peer_connect_target_rejects_metadata_ip() -> None:
    # Given: メタデータ IP の URL
    # When: resolve_peer_connect_target を呼ぶ
    # Then: None が返る
    settings = _network(allow_private_ips=True)
    assert (
        resolve_peer_connect_target("ws://169.254.169.254:80", settings, "development")
        is None
    )


@patch("useful_blockchain.network.peer_url.socket.getaddrinfo")
def test_resolve_peer_connect_target_pins_resolved_hostname(
    mock_getaddrinfo: MagicMock,
) -> None:
    # Given: hostname が公開 IP に解決される
    # When: resolve_peer_connect_target を呼ぶ
    # Then: 解決された IP がピンされる
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
    ]
    url = "ws://peer.example.com:8765"
    target = resolve_peer_connect_target(url, _network(), "development")
    assert target == PeerConnectTarget(
        url=url,
        host="8.8.8.8",
        port=8765,
        hostname="peer.example.com",
    )


@patch("useful_blockchain.network.peer_url.socket.getaddrinfo")
def test_resolve_peer_connect_target_rejects_restricted_resolved_ip(
    mock_getaddrinfo: MagicMock,
) -> None:
    # Given: hostname がループバック IP に解決される
    # When: resolve_peer_connect_target を呼ぶ
    # Then: None が返る
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
    ]
    assert (
        resolve_peer_connect_target(
            "ws://evil.example.com:8765", _network(), "development"
        )
        is None
    )


@patch("useful_blockchain.network.peer_url.socket.getaddrinfo")
def test_validate_and_resolve_use_same_dns_resolution(
    mock_getaddrinfo: MagicMock,
) -> None:
    # Given: DNS が公開 IP を返す
    # When: validate と resolve の両方を呼ぶ
    # Then: 両方とも許可され、同じ IP がピンされる
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0)),
    ]
    url = "ws://host.example.com:9000"
    settings = _network()
    assert validate_peer_url(url, settings, "development") == url
    target = resolve_peer_connect_target(url, settings, "development")
    assert target is not None
    assert target.host == "1.2.3.4"


@pytest.mark.asyncio
@patch("useful_blockchain.network.peer.websockets.connect", new_callable=AsyncMock)
async def test_connect_to_peer_passes_pinned_host_and_port(
    mock_connect: AsyncMock,
) -> None:
    # Given: ピンされた接続先
    # When: connect_to_peer を呼ぶ
    # Then: websockets.connect に host/port が渡される
    mock_connect.return_value = MagicMock()
    target = PeerConnectTarget(
        url="ws://peer.example.com:8765",
        host="8.8.8.8",
        port=8765,
        hostname="peer.example.com",
    )

    async def _noop(_peer_id: str, _msg_type: object, _payload: object) -> None:
        return None

    await connect_to_peer(
        "ws://peer.example.com:8765",
        "peer-1",
        _noop,
        connect_target=target,
    )

    mock_connect.assert_awaited_once()
    _, kwargs = mock_connect.call_args
    assert kwargs["host"] == "8.8.8.8"
    assert kwargs["port"] == 8765
