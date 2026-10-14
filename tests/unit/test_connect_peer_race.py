from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from useful_blockchain.network.node import Node


class _FakeP2P:
    local_url = "ws://127.0.0.1:9000"

    def __init__(self) -> None:
        self.connect_calls: list[str] = []

    async def connect_peer(self, url: str) -> str | None:
        self.connect_calls.append(url)
        await asyncio.sleep(0.05)
        return f"peer-{len(self.connect_calls)}"

    async def send_to_peer(self, *args, **kwargs) -> None:
        return


def _make_node(p2p: _FakeP2P) -> Node:
    node = Node.__new__(Node)
    node.p2p = p2p
    node._reconnect = SimpleNamespace(
        should_retry=lambda url: True,
        record_success=lambda url: None,
        record_failure=lambda url: None,
    )
    node._active_urls = set()
    node._connecting_urls = set()
    node._url_by_peer = {}
    node.discovery = SimpleNamespace(known_peers=[])
    node.settings = SimpleNamespace(
        network=SimpleNamespace(peer_auth=SimpleNamespace(enabled=False))
    )

    async def _noop_send_hello(_peer_id: str) -> None:
        return None

    node._send_hello = _noop_send_hello  # type: ignore[method-assign]
    return node


@pytest.mark.asyncio
async def test_concurrent_connect_peer_deduplicates_same_url() -> None:
    # Given: ハンドシェイクに時間がかかる接続先
    # When: 同一 URL へ connect_peer を並行実行する
    # Then: p2p.connect_peer は 1 回のみ呼ばれ、以降の重複呼び出しも接続しない
    p2p = _FakeP2P()
    node = _make_node(p2p)

    await asyncio.gather(
        node.connect_peer("ws://peer-a:9000"),
        node.connect_peer("ws://peer-a:9000"),
    )
    await node.connect_peer("ws://peer-a:9000")

    assert p2p.connect_calls == ["ws://peer-a:9000"]
    assert node._active_urls == {"ws://peer-a:9000"}


@pytest.mark.asyncio
async def test_connect_peer_failure_clears_in_flight_state() -> None:
    # Given: 接続に失敗する接続先
    # When: connect_peer を 2 回順に呼ぶ
    # Then: in-flight 状態が除去され 2 回目も再試行される
    p2p = _FakeP2P()

    async def fail_connect(url: str) -> None:
        p2p.connect_calls.append(url)
        await asyncio.sleep(0.01)
        return None

    p2p.connect_peer = fail_connect  # type: ignore[method-assign]
    node = _make_node(p2p)

    await node.connect_peer("ws://peer-a:9000")
    await node.connect_peer("ws://peer-a:9000")

    assert len(p2p.connect_calls) == 2
    assert node._active_urls == set()
