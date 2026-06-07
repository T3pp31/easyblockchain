"""ピア URL 検証のユニットテスト。"""

from __future__ import annotations

import pytest

from useful_blockchain.network.discovery import PeerDiscovery
from useful_blockchain.network.peer_url import validate_peer_url
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
