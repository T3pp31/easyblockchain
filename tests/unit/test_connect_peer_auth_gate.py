from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from useful_blockchain.network.messages import MessageType
from useful_blockchain.network.node import Node


class _FakePeer:
    def __init__(self) -> None:
        self.closed = False
        self.authenticated = False
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        self.closed = True


class _FakeP2P:
    local_url = "ws://127.0.0.1:9000"

    def __init__(self) -> None:
        self.peers: dict[str, _FakePeer] = {}
        self.sent: list[tuple[str, MessageType]] = []

    async def connect_peer(self, url: str) -> str | None:
        peer_id = f"peer-{len(self.peers) + 1}"
        self.peers[peer_id] = _FakePeer()
        return peer_id

    async def send_to_peer(self, peer_id: str, msg_type: MessageType, _payload) -> None:
        self.sent.append((peer_id, msg_type))


def _make_node(p2p: _FakeP2P, auth_enabled: bool) -> Node:
    node = Node.__new__(Node)
    node.p2p = p2p
    node._active_urls = set()
    node._url_by_peer = {}
    node._reconnect = SimpleNamespace(
        should_retry=lambda url: True,
        record_success=lambda url: None,
        record_failure=lambda url: None,
    )
    node.discovery = SimpleNamespace(known_peers=[])
    node.settings = SimpleNamespace(
        network=SimpleNamespace(peer_auth=SimpleNamespace(enabled=auth_enabled))
    )

    async def _noop_send_hello(_peer_id: str) -> None:
        return None

    node._send_hello = _noop_send_hello  # type: ignore[method-assign]
    return node


@pytest.mark.asyncio
async def test_unauthenticated_peer_not_sent_peers_and_closed() -> None:
    # Given: ピア認証が有効で、認証が完了しないピア
    # When: connect_peer を呼ぶ
    # Then: PEERS は送信されず、ピアは close される
    p2p = _FakeP2P()
    node = _make_node(p2p, auth_enabled=True)

    async def _never_authenticated(_peer_id: str, _timeout: float = 5.0) -> bool:
        return False

    node._wait_for_peer_authenticated = _never_authenticated  # type: ignore[method-assign]

    await node.connect_peer("ws://peer-a:9000")

    assert p2p.sent == []
    assert p2p.peers["peer-1"].close_calls == 1


@pytest.mark.asyncio
async def test_unauthenticated_peer_cleanup_on_timeout() -> None:
    # Given: 認証が完了しないピア
    # When: connect_peer を呼ぶ
    # Then: 接続管理状態から URL とピアが除去され、failure が記録される
    p2p = _FakeP2P()
    node = _make_node(p2p, auth_enabled=True)
    failures: list[str] = []
    node._reconnect = SimpleNamespace(
        should_retry=lambda url: True,
        record_success=lambda url: None,
        record_failure=lambda url: failures.append(url),
    )

    async def _never_authenticated(_peer_id: str, _timeout: float = 5.0) -> bool:
        return False

    node._wait_for_peer_authenticated = _never_authenticated  # type: ignore[method-assign]

    await node.connect_peer("ws://peer-a:9000")

    assert "ws://peer-a:9000" not in node._active_urls
    assert "peer-1" not in node._url_by_peer
    assert failures == ["ws://peer-a:9000"]
    assert p2p.peers["peer-1"].close_calls == 1


@pytest.mark.asyncio
async def test_wait_for_peer_authenticated_returns_false_after_timeout() -> None:
    # Given: 認証が完了しないピア
    # When: _wait_for_peer_authenticated をタイムアウト付きで呼ぶ
    # Then: False が返る
    p2p = _FakeP2P()
    node = _make_node(p2p, auth_enabled=True)

    assert await node._wait_for_peer_authenticated("peer-1", timeout=0.1) is False


@pytest.mark.asyncio
async def test_wait_for_peer_authenticated_returns_false_when_peer_closed() -> None:
    # Given: 認証前に切断済みのピア
    # When: _wait_for_peer_authenticated を呼ぶ
    # Then: False が返る
    p2p = _FakeP2P()
    node = _make_node(p2p, auth_enabled=True)
    await p2p.connect_peer("ws://peer-a:9000")
    p2p.peers["peer-1"].closed = True

    assert await node._wait_for_peer_authenticated("peer-1", timeout=1.0) is False


@pytest.mark.asyncio
async def test_authenticated_peer_receives_peers_message() -> None:
    # Given: ピア認証が有効で、待機中に認証が完了するピア
    # When: connect_peer を呼ぶ
    # Then: PEERS が送信され、ピアは close されない
    p2p = _FakeP2P()
    node = _make_node(p2p, auth_enabled=True)

    async def _complete_auth_later() -> None:
        await asyncio.sleep(0.05)
        p2p.peers["peer-1"].authenticated = True

    marker = asyncio.create_task(_complete_auth_later())

    await node.connect_peer("ws://peer-a:9000")
    await marker

    assert p2p.sent == [("peer-1", MessageType.PEERS)]
    assert p2p.peers["peer-1"].close_calls == 0


@pytest.mark.asyncio
async def test_peers_sent_without_auth_gate_when_auth_disabled() -> None:
    # Given: ピア認証が無効
    # When: connect_peer を呼ぶ
    # Then: 認証待ちなしで PEERS が送信される
    p2p = _FakeP2P()
    node = _make_node(p2p, auth_enabled=False)

    await node.connect_peer("ws://peer-a:9000")

    assert p2p.sent == [("peer-1", MessageType.PEERS)]
