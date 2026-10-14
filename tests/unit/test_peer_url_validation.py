"""ピア URL 検証のユニットテスト。"""

from __future__ import annotations
import websockets

import socket
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from useful_blockchain.network.discovery import PeerDiscovery
from useful_blockchain.network.peer import connect_to_peer
from useful_blockchain.network.peer_url import (
    PeerConnectTarget,
    resolve_peer_connect_target,
    validate_peer_url,
)
from useful_blockchain.types import NetworkSettings, PeerConnectSettings, TlsSettings


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
        ("ws://100.64.1.1:8765", None),
        ("ws://0177.0.0.1:8765", None),
        ("http://8.8.8.8:8765", None),
        ("ws://8.8.8.8:8765/extra", None),
        ("ws://user@8.8.8.8:8765", None),
        ("ws://8.8.8.8:8765?foo=bar", None),
        ("ws://8.8.8.8:8765?a=1&b=2", None),
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


@pytest.mark.parametrize(
    "url",
    [
        "ws://[::1:8765",
        "ws://8.8.8.8:99999",
        "ws://8.8.8.8:abc",
    ],
)
def test_validate_peer_url_rejects_malformed_urls_without_exception(url: str) -> None:
    # Given: 未閉括弧 IPv6 や不正ポートを含む URL
    # When: validate_peer_url を呼ぶ
    # Then: 例外ではなく None が返る
    assert validate_peer_url(url, _network(), "development") is None


@pytest.mark.parametrize(
    "url",
    [
        "ws://[::1:8765",
        "ws://8.8.8.8:99999",
        "ws://8.8.8.8:abc",
    ],
)
async def test_resolve_peer_connect_target_rejects_malformed_urls_without_exception(
    url: str,
) -> None:
    # Given: 未閉括弧 IPv6 や不正ポートを含む URL
    # When: resolve_peer_connect_target を呼ぶ
    # Then: 例外ではなく None が返る
    assert await resolve_peer_connect_target(url, _network(), "development") is None


@pytest.mark.parametrize(
    "url",
    [
        "ws://100.63.255.255:8765",
        "ws://100.128.0.0:8765",
    ],
)
def test_validate_peer_url_allows_cgnat_boundary_ips(url: str) -> None:
    # Given: CGNAT レンジ外の境界 IP
    # When: validate_peer_url を呼ぶ
    # Then: URL が返る
    assert validate_peer_url(url, _network(), "development") == url


async def test_resolve_peer_connect_target_rejects_cgnat_ip() -> None:
    # Given: CGNAT レンジ内の IP
    # When: resolve_peer_connect_target を呼ぶ
    # Then: None が返る
    assert (
        await resolve_peer_connect_target(
            "ws://100.64.1.1:8765", _network(), "development"
        )
        is None
    )


async def test_resolve_peer_connect_target_rejects_query_string() -> None:
    # Given: クエリ文字列付きの WebSocket URL
    # When: resolve_peer_connect_target を呼ぶ
    # Then: None が返る
    assert (
        await resolve_peer_connect_target(
            "ws://8.8.8.8:8765?foo=bar", _network(), "development"
        )
        is None
    )


async def test_resolve_peer_connect_target_rejects_ambiguous_ipv4_notation() -> None:
    # Given: 先頭ゼロ付き IPv4 リテラル
    # When: resolve_peer_connect_target を呼ぶ
    # Then: None が返る
    assert (
        await resolve_peer_connect_target(
            "ws://0177.0.0.1:8765", _network(), "development"
        )
        is None
    )


def test_validate_peer_url_allows_private_ip_when_enabled() -> None:
    # Given: allow_private_ips=true かつ blocked_cidrs 未設定
    # When: ループバック URL を検証する
    # Then: URL が返る
    url = "ws://127.0.0.1:8765"
    settings = _network(allow_private_ips=True, blocked_cidrs=[])
    assert validate_peer_url(url, settings, "development") == url


def test_validate_peer_url_blocks_metadata_ip_even_when_private_allowed() -> None:
    # Given: allow_private_ips=true でもメタデータ IP は拒否
    # When: メタデータ URL を検証する
    # Then: None が返る
    url = "ws://169.254.169.254:80"
    settings = _network(allow_private_ips=True)
    assert validate_peer_url(url, settings, "development") is None


def test_validate_peer_url_blocks_ipv4_mapped_metadata_ip() -> None:
    # Given: allow_private_ips=true でも IPv4-mapped IPv6 形式のメタデータ IP は拒否
    # When: ::ffff:169.254.169.254 を検証する
    # Then: None が返る
    settings = _network(allow_private_ips=True)
    assert (
        validate_peer_url(
            "ws://[::ffff:169.254.169.254]:80", settings, "development"
        )
        is None
    )


def test_validate_peer_url_blocks_ipv6_metadata_endpoint() -> None:
    # Given: allow_private_ips=true でも IPv6 メタデータエンドポイントは拒否
    # When: fd00:ec2::254 を検証する
    # Then: None が返る
    settings = _network(allow_private_ips=True)
    assert (
        validate_peer_url("ws://[fd00:ec2::254]:80", settings, "development") is None
    )


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
            blocked_cidrs=[],
            max_peers_per_message=2,
            allowed_ports=[80, 443, 8765, 8766, 8767],
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


async def test_resolve_peer_connect_target_pins_literal_public_ip() -> None:
    # Given: 公開 IP のリテラル URL
    # When: resolve_peer_connect_target を呼ぶ
    # Then: ピンされた接続先が返る
    url = "ws://8.8.8.8:8765"
    target = await resolve_peer_connect_target(url, _network(), "development")
    assert target == PeerConnectTarget(
        url=url,
        host="8.8.8.8",
        port=8765,
        hostname="8.8.8.8",
    )


async def test_resolve_peer_connect_target_rejects_restricted_ip() -> None:
    # Given: ループバック IP の URL
    # When: resolve_peer_connect_target を呼ぶ
    # Then: None が返る
    assert (
        await resolve_peer_connect_target(
            "ws://127.0.0.1:8765", _network(), "development"
        )
        is None
    )


async def test_resolve_peer_connect_target_rejects_metadata_ip() -> None:
    # Given: メタデータ IP の URL
    # When: resolve_peer_connect_target を呼ぶ
    # Then: None が返る
    settings = _network(allow_private_ips=True)
    assert (
        await resolve_peer_connect_target(
            "ws://169.254.169.254:80", settings, "development"
        )
        is None
    )


async def test_resolve_peer_connect_target_rejects_mapped_metadata_ip() -> None:
    # Given: IPv4-mapped IPv6 形式のメタデータ URL
    # When: resolve_peer_connect_target を呼ぶ
    # Then: None が返る
    settings = _network(allow_private_ips=True)
    assert (
        await resolve_peer_connect_target(
            "ws://[::ffff:169.254.169.254]:80", settings, "development"
        )
        is None
    )


async def test_resolve_peer_connect_target_rejects_ipv6_metadata_endpoint() -> None:
    # Given: IPv6 メタデータエンドポイントの URL
    # When: resolve_peer_connect_target を呼ぶ
    # Then: None が返る
    settings = _network(allow_private_ips=True)
    assert (
        await resolve_peer_connect_target(
            "ws://[fd00:ec2::254]:80", settings, "development"
        )
        is None
    )


def test_validate_peer_url_fail_closed_on_unicode_error() -> None:
    # Given: getaddrinfo が UnicodeError を送出するホスト名
    # When: validate_peer_url を呼ぶ
    # Then: 例外は漏れず None が返る
    with patch(
        "useful_blockchain.network.peer_url.socket.getaddrinfo",
        side_effect=UnicodeError("label empty or too long"),
    ) as mock_getaddrinfo:
        assert (
            validate_peer_url("ws://例..example.com:8765", _network(), "development")
            is None
        )
        # モック経路（_resolve_peer_ips）に到達したことを保証する
        mock_getaddrinfo.assert_called()


def test_validate_peer_url_fail_closed_on_too_long_label() -> None:
    # Given: 64 文字超のラベルを持つホスト名（IDNA エンコードで確定的に UnicodeError）
    # When: validate_peer_url を呼ぶ
    # Then: 例外は漏れず None が返る
    url = f"ws://{'a' * 64}.com:8765"
    assert validate_peer_url(url, _network(), "development") is None


@patch("useful_blockchain.network.peer_url.socket.getaddrinfo")
async def test_resolve_peer_connect_target_pins_resolved_hostname(
    mock_getaddrinfo: MagicMock,
) -> None:
    # Given: hostname が公開 IP に解決される
    # When: resolve_peer_connect_target を呼ぶ
    # Then: 解決された IP がピンされる
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
    ]
    url = "ws://peer.example.com:8765"
    target = await resolve_peer_connect_target(url, _network(), "development")
    assert target == PeerConnectTarget(
        url=url,
        host="8.8.8.8",
        port=8765,
        hostname="peer.example.com",
    )


@patch("useful_blockchain.network.peer_url.socket.getaddrinfo")
async def test_resolve_peer_connect_target_resolves_dns_off_event_loop(
    mock_getaddrinfo: MagicMock,
) -> None:
    # Given: DNS 解決時に呼び出し元スレッドを記録する getaddrinfo
    # When: resolve_peer_connect_target を呼ぶ
    # Then: DNS 解決はイベントループスレッド外で実行される
    dns_thread_idents: set[int] = set()

    def _record_thread(*args: object, **kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        dns_thread_idents.add(threading.get_ident())
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]

    mock_getaddrinfo.side_effect = _record_thread
    url = "ws://peer.example.com:8765"
    target = await resolve_peer_connect_target(url, _network(), "development")
    assert target is not None
    assert dns_thread_idents
    assert dns_thread_idents != {threading.get_ident()}


@patch("useful_blockchain.network.peer_url.socket.getaddrinfo")
async def test_resolve_peer_connect_target_rejects_restricted_resolved_ip(
    mock_getaddrinfo: MagicMock,
) -> None:
    # Given: hostname がループバック IP に解決される
    # When: resolve_peer_connect_target を呼ぶ
    # Then: None が返る
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
    ]
    assert (
        await resolve_peer_connect_target(
            "ws://evil.example.com:8765", _network(), "development"
        )
        is None
    )


@patch("useful_blockchain.network.peer_url.socket.getaddrinfo")
async def test_validate_and_resolve_use_same_dns_resolution(
    mock_getaddrinfo: MagicMock,
) -> None:
    # Given: DNS が公開 IP を返す
    # When: validate と resolve の両方を呼ぶ
    # Then: 両方とも許可され、同じ IP がピンされる
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0)),
    ]
    url = "ws://host.example.com:8765"
    settings = _network()
    assert validate_peer_url(url, settings, "development") == url
    target = await resolve_peer_connect_target(url, settings, "development")
    assert target is not None
    assert target.host == "1.2.3.4"


def test_validate_peer_url_allows_port_8765() -> None:
    # Given: 許可ポート 8765 の公開 IP URL
    # When: validate_peer_url を呼ぶ
    # Then: URL が返る
    url = "ws://8.8.8.8:8765"
    assert validate_peer_url(url, _network(), "development") == url


def test_validate_peer_url_rejects_disallowed_port_22() -> None:
    # Given: 許可リストにないポート 22
    # When: validate_peer_url を呼ぶ
    # Then: None が返る
    url = "ws://8.8.8.8:22"
    assert validate_peer_url(url, _network(), "development") is None


def test_validate_peer_url_allows_ephemeral_port_for_private_ip_when_enabled() -> None:
    # Given: allow_private_ips=true かつ blocked_cidrs 未設定、エフェメラルポート
    # When: ループバック URL を検証する
    # Then: URL が返る
    url = "ws://127.0.0.1:36861"
    settings = _network(allow_private_ips=True, blocked_cidrs=[])
    assert validate_peer_url(url, settings, "development") == url


def test_validate_peer_url_allows_default_port_80_for_ws() -> None:
    # Given: 明示ポートなしの ws:// URL（デフォルト 80）
    # When: validate_peer_url を呼ぶ
    # Then: URL が返る
    url = "ws://8.8.8.8"
    assert validate_peer_url(url, _network(), "development") == url


def test_validate_peer_url_allows_default_port_443_for_wss() -> None:
    # Given: 明示ポートなしの wss:// URL（デフォルト 443）
    # When: validate_peer_url を呼ぶ
    # Then: URL が返る
    settings = NetworkSettings(tls=TlsSettings(enabled=True))
    url = "wss://8.8.8.8"
    assert validate_peer_url(url, settings, "production") == url


def test_validate_peer_url_respects_custom_allowed_ports() -> None:
    # Given: カスタム allowed_ports=[9000]
    # When: ポート 9000 の URL を検証する
    # Then: 許可され、8765 は拒否される
    settings = _network(allowed_ports=[9000])
    assert validate_peer_url("ws://8.8.8.8:9000", settings, "development") == "ws://8.8.8.8:9000"
    assert validate_peer_url("ws://8.8.8.8:8765", settings, "development") is None


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


def test_validate_peer_url_blocks_blocked_cidrs_even_when_private_allowed() -> None:
    # Given: allow_private_ips=true かつ blocked_cidrs に該当 CIDR を設定
    # When: blocked_cidrs 内の IP の URL を検証する
    # Then: None が返る
    url = "ws://10.0.0.1:8765"
    settings = _network(allow_private_ips=True, blocked_cidrs=["10.0.0.0/8"])
    assert validate_peer_url(url, settings, "development") is None

def test_validate_peer_url_blocks_blocked_public_cidr() -> None:
    # Given: blocked_cidrs にパブリック CIDR を設定
    # When: 該当するパブリック IP の URL を検証する
    # Then: None が返る
    url = "ws://203.0.113.10:8765"
    settings = _network(blocked_cidrs=["203.0.113.0/24"])
    assert validate_peer_url(url, settings, "development") is None

def test_validate_peer_url_allows_non_blocked_private_ip_when_private_allowed() -> None:
    # Given: allow_private_ips=true かつ blocked_cidrs に別レンジを設定
    # When: blocked_cidrs 外のプライベート IP の URL を検証する
    # Then: URL が返る
    url = "ws://192.168.1.10:8765"
    settings = _network(allow_private_ips=True, blocked_cidrs=["10.0.0.0/8"])
    assert validate_peer_url(url, settings, "development") == url


@pytest.mark.asyncio
async def test_websockets_connect_pinned_host_and_port_overrides_uri() -> None:
    # Given: 127.0.0.1 でのみ待ち受ける実 WebSocket サーバー
    # When: URI には待受されていない [::1] を指定し、host/port kwargs でピン留めする
    # Then: 実ライブラリで上書きが機能し実接続が成立する
    # （websockets.connect は host/port kwargs をループの接続先オーバーライドとして
    #   公開しており、websockets 15.0.1 / 16.1.1 / 17.2 の実接続で確認済み）
    async def handler(websocket) -> None:
        await websocket.send("pinned")
        await websocket.wait_closed()

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        async with websockets.connect(
            f"ws://[::1]:{port}",
            host="127.0.0.1",
            port=port,
        ) as websocket:
            assert await websocket.recv() == "pinned"


@pytest.mark.parametrize("host", ["100.64.0.1", "100.100.100.200", "100.127.255.254", "[::ffff:100.100.100.200]"])
def test_shared_address_space_rejected_without_explicit_cidr(host):
    from useful_blockchain.types import NetworkSettings, PeerConnectSettings
    # Given: CIDR 制限リストが空でプライベート IP を拒否する設定
    settings = NetworkSettings(peer_connect=PeerConnectSettings(blocked_cidrs=[]))
    # When: 共有アドレス・IPv4-mapped IPv6 を検証する
    # Then: 非グローバルアドレスへの接続を拒否する
    assert validate_peer_url(f"ws://{host}:8765", settings, "development") is None


def test_shared_address_space_can_be_opted_into_in_development():
    from useful_blockchain.types import NetworkSettings, PeerConnectSettings
    # Given: 開発環境で明示的に非グローバル IP を許可する設定
    settings = NetworkSettings(peer_connect=PeerConnectSettings(
        blocked_cidrs=[], allow_private_ips=True
    ))
    # When: 共有アドレスを検証する
    # Then: 開発環境向けの既存オプトインを維持する
    url = "ws://100.64.0.1:8765"
    assert validate_peer_url(url, settings, "development") == url
