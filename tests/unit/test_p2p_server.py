import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
import websockets

from useful_blockchain.network.messages import MessageType
from useful_blockchain.network.server import P2PServer
from useful_blockchain.types import NetworkSettings, TlsSettings


async def _noop_handler(_peer_id: str, _msg_type: MessageType, _payload: dict) -> None:
    return None


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
    await asyncio.sleep(0.05)

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
    await asyncio.sleep(0.05)
    assert len(server.peers) == 2

    with pytest.raises(websockets.exceptions.ConnectionClosed) as exc_info:
        ws3 = await websockets.connect(url)
        await ws3.recv()

    assert exc_info.value.rcvd.code == 1013

    await asyncio.sleep(0.05)
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
    await asyncio.sleep(0.05)
    assert len(server.peers) == 1

    peer_id = await server.connect_peer(url)
    assert peer_id is None
    assert len(server.peers) == 1

    await ws.close()
    await server.stop()


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
            self.remote_address = ("127.0.0.1", 9999)

        async def close(self, code: int | None = None, reason: str = "") -> None:
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
