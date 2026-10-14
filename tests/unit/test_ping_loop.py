import asyncio
import time

import pytest
from types import SimpleNamespace

from useful_blockchain.network.node import Node
from useful_blockchain.network.peer import PeerConnection


async def _noop_on_message(peer_id, msg_type, payload):
    return None


async def _noop_ws_close(code=1000, reason=""):
    return None


def _make_peer(peer_id):
    websocket = SimpleNamespace(close=_noop_ws_close)
    return PeerConnection(peer_id, websocket, _noop_on_message, require_auth=False)


def _make_node(peers, pong_timeout, ping_interval, on_pong_timeout=None):
    node = Node.__new__(Node)
    node._running = True
    node.settings = SimpleNamespace(
        network=SimpleNamespace(
            pong_timeout_seconds=pong_timeout,
            ping_interval_seconds=ping_interval,
        )
    )
    node.p2p = SimpleNamespace(peers=peers)
    node.node_id = "test-node"
    node._metrics = SimpleNamespace(
        inc_pong_timeouts=on_pong_timeout if on_pong_timeout else lambda: None
    )
    node._update_metrics = lambda: None
    return node


async def _run_loop(node, stop_after):
    state = {"count": 0}

    async def broadcast(msg_type, payload):
        state["count"] += 1
        if state["count"] >= stop_after:
            node._running = False

    node.p2p.broadcast = broadcast

    await asyncio.wait_for(node._ping_loop(), timeout=5)
    return state["count"]


@pytest.mark.asyncio
async def test_outstanding_ping_timestamp_not_refreshed():
    t0 = time.monotonic()
    answered = _make_peer("answered")
    answered.last_ping_at = t0 - 10
    answered.last_pong_at = t0 - 9
    stalled = _make_peer("stalled")
    stalled.last_ping_at = t0 - 1.0
    stalled.last_pong_at = t0 - 2.0

    node = _make_node(
        {"answered": answered, "stalled": stalled},
        pong_timeout=10.0,
        ping_interval=0.01,
    )
    await _run_loop(node, stop_after=3)

    assert stalled.closed is False
    assert stalled.last_ping_at == t0 - 1.0
    assert answered.last_ping_at >= t0


@pytest.mark.asyncio
async def test_unanswered_ping_times_out_after_pong_timeout():
    t0 = time.monotonic()
    peer = _make_peer("stalled")
    peer.last_ping_at = t0 - 2.5
    peer.last_pong_at = t0 - 2.6
    timeout_calls = []

    node = _make_node(
        {"stalled": peer},
        pong_timeout=3.0,
        ping_interval=0.01,
        on_pong_timeout=lambda: timeout_calls.append(1),
    )
    await _run_loop(node, stop_after=100)

    assert peer.closed is True
    assert len(timeout_calls) == 1


@pytest.mark.asyncio
async def test_pong_timeout_fires_even_when_ping_interval_is_short():
    peer = _make_peer("stalled")
    t0 = time.monotonic()
    peer.last_pong_at = t0 - 1.0
    timeout_calls = []

    node = _make_node(
        {"stalled": peer},
        pong_timeout=0.05,
        ping_interval=0.01,
        on_pong_timeout=lambda: timeout_calls.append(1),
    )
    await _run_loop(node, stop_after=30)

    assert peer.closed is True
    assert timeout_calls


@pytest.mark.asyncio
async def test_peer_that_never_ponged_is_disconnected_on_timeout():
    peer = _make_peer("silent")
    t0 = time.monotonic()
    peer.last_ping_at = t0 - 10
    timeout_calls = []

    node = _make_node(
        {"silent": peer},
        pong_timeout=0.5,
        ping_interval=0.05,
        on_pong_timeout=lambda: timeout_calls.append(1),
    )
    await _run_loop(node, stop_after=3)

    assert peer.closed is True
    assert len(timeout_calls) == 1

@pytest.mark.asyncio
async def test_never_pinged_peer_is_not_disconnected():
    peer = _make_peer("fresh")

    node = _make_node({"fresh": peer}, pong_timeout=5.0, ping_interval=0.01)
    await _run_loop(node, stop_after=3)

    assert peer.closed is False

@pytest.mark.asyncio
async def test_answered_peer_is_not_disconnected():
    peer = _make_peer("healthy")
    t0 = time.monotonic()
    peer.last_ping_at = t0 - 10
    peer.last_pong_at = t0 - 9

    node = _make_node({"healthy": peer}, pong_timeout=0.5, ping_interval=0.01)
    await _run_loop(node, stop_after=3)

    assert peer.closed is False
