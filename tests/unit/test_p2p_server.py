from __future__ import annotations
from useful_blockchain.types import PeerConnectSettings
from types import SimpleNamespace
from useful_blockchain.network.peer import PeerConnection
import asyncio
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
import websockets

from useful_blockchain.network.messages import MessageType, encode_message
from useful_blockchain.network.server import P2PServer
from useful_blockchain.types import NetworkSettings, PeerAuthSettings, TlsSettings


async def _noop_handler(_peer_id: str, _msg_type: MessageType, _payload: dict) -> None:
    return None


async def _wait_for_peers(
    server: P2PServer,
    count: int,
    timeout: float = 5.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while len(server.peers) < count:
        if asyncio.get_running_loop().time() >= deadline:
            pytest.fail(
                f"peers did not reach {count} within {timeout}s "
                f"(current: {len(server.peers)})"
            )
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_inbound_connection_accepted_below_max_peers() -> None:
    # Given: max_peers=2 のサーバー
    # When: 1 件のインバウンド接続を行う
    # Then: peers に登録される
    settings = NetworkSettings(host="127.0.0.1", port=0, max_peers=2)
    server = P2PServer(settings, "node-1", _noop_handler)
    await server.start()

    url = f"ws://127.0.0.1:{server._actual_port}"
    ws = await websockets.connect(url)
    await _wait_for_peers(server, 1)

    assert len(server.peers) == 1

    await ws.close()
    await server.stop()


@pytest.mark.asyncio
async def test_inbound_connection_rejected_at_max_peers() -> None:
    # Given: max_peers=2 で既に 2 接続があるサーバー
    # When: 3 件目のインバウンド接続を試みる
    # Then: peers 数は 2 のまま、接続は拒否される
    settings = NetworkSettings(host="127.0.0.1", port=0, max_peers=2)
    server = P2PServer(settings, "node-1", _noop_handler)
    await server.start()

    url = f"ws://127.0.0.1:{server._actual_port}"
    ws1 = await websockets.connect(url)
    ws2 = await websockets.connect(url)
    await _wait_for_peers(server, 2)
    assert len(server.peers) == 2

    with pytest.raises(websockets.exceptions.ConnectionClosed) as exc_info:
        ws3 = await websockets.connect(url)
        await ws3.recv()

    assert exc_info.value.rcvd.code == 1013

    await _wait_for_peers(server, 2)
    assert len(server.peers) == 2

    await ws1.close()
    await ws2.close()
    await server.stop()


@pytest.mark.asyncio
async def test_outbound_connect_peer_returns_none_at_max_peers() -> None:
    # Given: max_peers=1 で既に 1 接続があるサーバー
    # When: connect_peer を呼ぶ
    # Then: None が返る
    settings = NetworkSettings(host="127.0.0.1", port=0, max_peers=1)
    server = P2PServer(settings, "node-1", _noop_handler)
    await server.start()

    url = f"ws://127.0.0.1:{server._actual_port}"
    ws = await websockets.connect(url)
    await _wait_for_peers(server, 1)
    assert len(server.peers) == 1

    peer_id = await server.connect_peer(url)
    assert peer_id is None
    assert len(server.peers) == 1

    await ws.close()
    await server.stop()


@pytest.mark.asyncio
async def test_connect_peer_rejects_plain_ws_when_tls_enabled(tmp_path: Path) -> None:
    # Given: TLS 有効なサーバー
    # When: ws:// へ connect_peer を呼ぶ
    # Then: None が返り接続しない
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("dummy")
    key.write_text("dummy")
    settings = NetworkSettings(
        host="127.0.0.1",
        port=0,
        tls=TlsSettings(enabled=True, cert_file=str(cert), key_file=str(key)),
    )
    with patch("ssl.SSLContext.load_cert_chain"):
        server = P2PServer(settings, "node-1", _noop_handler)
    peer_id = await server.connect_peer("ws://127.0.0.1:8765")
    assert peer_id is None


@pytest.mark.asyncio
async def test_connect_peer_rejects_plain_ws_in_production() -> None:
    # Given: production 環境（TLS 無効でも平文拒否）
    # When: ws:// へ connect_peer を呼ぶ
    # Then: None が返る
    settings = NetworkSettings(host="127.0.0.1", port=0)
    server = P2PServer(settings, "node-1", _noop_handler, environment="production")
    peer_id = await server.connect_peer("ws://127.0.0.1:8765")
    assert peer_id is None


async def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


@pytest.mark.asyncio
async def test_unauthenticated_connection_closed_after_handshake_timeout() -> None:
    # Given: handshake_timeout_seconds が短いサーバー
    # When: HELLO を送らずに接続を維持する
    # Then: 1008 で切断され peers から削除される
    settings = NetworkSettings(
        host="127.0.0.1",
        port=0,
        peer_auth=PeerAuthSettings(enabled=True, handshake_timeout_seconds=0.2),
    )
    server = P2PServer(settings, "node-1", _noop_handler)
    await server.start()

    url = f"ws://127.0.0.1:{server._actual_port}"
    ws = await websockets.connect(url)
    assert await _wait_until(lambda: len(server.peers) == 1)

    with pytest.raises(websockets.exceptions.ConnectionClosed) as exc_info:
        await ws.recv()

    assert exc_info.value.rcvd.code == 1008

    assert await _wait_until(lambda: len(server.peers) == 0)

    await server.stop()


@pytest.mark.asyncio
async def test_peer_removed_without_timeout_when_disconnected_before_auth() -> None:
    # Given: handshake_timeout_seconds が長いサーバー
    # When: クライアントが HELLO 送信前に切断する
    # Then: handshake_timeout を待たずに peers から削除される
    settings = NetworkSettings(
        host="127.0.0.1",
        port=0,
        peer_auth=PeerAuthSettings(enabled=True, handshake_timeout_seconds=30.0),
    )
    server = P2PServer(settings, "node-1", _noop_handler)
    await server.start()

    url = f"ws://127.0.0.1:{server._actual_port}"
    ws = await websockets.connect(url)
    assert await _wait_until(lambda: len(server.peers) == 1)

    await ws.close()
    assert await _wait_until(lambda: len(server.peers) == 0)

    await server.stop()


@pytest.mark.asyncio
async def test_connection_kept_when_authenticated_within_handshake_timeout() -> None:
    # Given: HELLO 受信時に認証を完了するハンドラ
    # When: HELLO を送信する
    # Then: handshake_timeout 経過後も接続が維持される
    settings = NetworkSettings(
        host="127.0.0.1",
        port=0,
        peer_auth=PeerAuthSettings(enabled=True, handshake_timeout_seconds=0.2),
    )

    async def authenticate_hello(peer_id: str, _msg_type: MessageType, _payload: dict) -> None:
        peer = server.peers.get(peer_id)
        if peer is not None:
            peer.mark_authenticated()

    server = P2PServer(settings, "node-1", authenticate_hello)
    await server.start()

    url = f"ws://127.0.0.1:{server._actual_port}"
    ws = await websockets.connect(url)
    await ws.send(encode_message(MessageType.HELLO, {}))

    assert await _wait_until(
        lambda: any(p.authenticated for p in server.peers.values())
    )
    # handshake_timeout (0.2s) 経過後も接続が維持されていることを確認する
    await asyncio.sleep(0.4)
    assert len(server.peers) == 1

    await ws.close()
    await server.stop()


def _make_fake_peer(peer_id: str, send_impl) -> PeerConnection:
    async def _noop_ws_close(code=1000, reason="") -> None:
        return None

    async def _noop_on_message(pid, msg_type, payload):
        return None

    peer = PeerConnection(
        peer_id,
        SimpleNamespace(close=_noop_ws_close),
        _noop_on_message,
        require_auth=False,
    )
    peer.send = send_impl
    return peer

@pytest.mark.asyncio
async def test_broadcast_closes_stuck_peer_and_continues_to_others() -> None:
    # Given: 送信が詰まったピアと正常なピア
    # When: broadcast を呼ぶ
    # Then: 詰まったピアはタイムアウトで close され、正常なピアへは送信される
    settings = NetworkSettings(
        host="127.0.0.1", port=0, broadcast_send_timeout_seconds=0.05
    )
    server = P2PServer(settings, "node-1", _noop_handler)

    sent: list[str] = []

    async def _fast_send(msg_type: MessageType, payload: dict) -> None:
        sent.append("fast")

    async def _stuck_send(msg_type: MessageType, payload: dict) -> None:
        await asyncio.sleep(30)

    stuck = _make_fake_peer("stuck", _stuck_send)
    fast = _make_fake_peer("fast", _fast_send)
    server.peers = {"stuck": stuck, "fast": fast}

    await asyncio.wait_for(
        server.broadcast(MessageType.NEW_BLOCK, {"index": 1}), timeout=2
    )

    assert sent == ["fast"]
    assert stuck.closed is True
    assert fast.closed is False


def test_local_url_wraps_ipv6_host_in_brackets() -> None:
    # Given: IPv6 リテラルのホスト設定
    # When: local_url を参照する
    # Then: ブラケット付きの有効な URL が返る
    settings = NetworkSettings(host="2001:db8::1", port=8765)
    server = P2PServer(settings, "node-1", _noop_handler)
    assert server.local_url == "ws://[2001:db8::1]:8765"

def test_local_url_maps_ipv6_wildcard_to_loopback() -> None:
    # Given: host="::"（全 IPv6 インターフェース）
    # When: local_url を参照する
    # Then: ループバック ::1 のブラケット付き URL が返る
    settings = NetworkSettings(host="::", port=8765)
    server = P2PServer(settings, "node-1", _noop_handler)
    assert server.local_url == "ws://[::1]:8765"

def test_local_url_keeps_ipv4_and_hostname_unchanged() -> None:
    # Given: IPv4 / ホスト名の設定
    # When: local_url を参照する
    # Then: 従来形式の URL が返る
    server_v4 = P2PServer(
        NetworkSettings(host="0.0.0.0", port=8765), "node-1", _noop_handler
    )
    assert server_v4.local_url == "ws://127.0.0.1:8765"
    server_name = P2PServer(
        NetworkSettings(host="node1.example.com", port=8765), "node-1", _noop_handler
    )
    assert server_name.local_url == "ws://node1.example.com:8765"


@pytest.mark.asyncio
async def test_rejected_inbound_does_not_hold_peer_lock_during_close() -> None:
    # Given: max_peers=0（全接続を拒否）と close に時間がかかる websocket
    # When: _handle_connection を呼ぶ
    # Then: close の完了を待たずに _peer_lock が解放される
    settings = NetworkSettings(host="127.0.0.1", port=0, max_peers=0)
    server = P2PServer(settings, "node-1", _noop_handler)

    class _SlowCloseWebSocket:
        def __init__(self) -> None:
            self.closed = False
            self.close_code: int | None = None
            self.remote_address = ("127.0.0.1", 9999)

        async def close(self, code: int | None = None, reason: str = "") -> None:
            self.close_code = code
            await asyncio.sleep(0.2)
            self.closed = True

    ws = _SlowCloseWebSocket()
    task = asyncio.create_task(server._handle_connection(ws))  # type: ignore[arg-type]
    await asyncio.sleep(0.05)
    assert ws.closed is False

    await asyncio.wait_for(server._peer_lock.acquire(), timeout=0.1)
    server._peer_lock.release()
    await task
    assert ws.closed is True
    assert ws.close_code == 1013

@pytest.mark.asyncio
async def test_rejected_outbound_does_not_hold_peer_lock_during_close() -> None:
    # Given: max_peers=1 と close に時間がかかるフェイク peer
    # （connect_to_peer 完了時に peers を満杯にし、2 回目のロック判定で拒否させる）
    # When: connect_peer を呼ぶ
    # Then: close の完了を待たずに _peer_lock が解放される
    settings = NetworkSettings(
        host="127.0.0.1",
        port=0,
        max_peers=1,
        peer_connect=PeerConnectSettings(allow_private_ips=True, blocked_cidrs=[]),
    )
    server = P2PServer(settings, "node-1", _noop_handler)

    class _SlowClosePeer:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            await asyncio.sleep(0.2)
            self.closed = True

    slow_peer = _SlowClosePeer()
    connected = asyncio.Event()

    async def _fake_connect_to_peer(*args: object, **kwargs: object) -> object:
        # 接続完了時に peers を満杯にする
        server.peers["inbound"] = slow_peer  # type: ignore[assignment]
        connected.set()
        return slow_peer

    with patch(
        "useful_blockchain.network.peer.connect_to_peer",
        side_effect=_fake_connect_to_peer,
    ):
        task = asyncio.create_task(server.connect_peer("ws://127.0.0.1:8765"))
        await connected.wait()
        assert slow_peer.closed is False

        await asyncio.wait_for(server._peer_lock.acquire(), timeout=0.1)
        server._peer_lock.release()

        assert await task is None
        assert slow_peer.closed is True
        assert len(server.peers) == 1
