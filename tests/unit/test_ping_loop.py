import asyncio
import time
from types import SimpleNamespace

from useful_blockchain.network.node import Node
from useful_blockchain.network.peer import PeerConnection


async def _noop_on_message(peer_id, msg_type, payload):
    return None


async def _noop_ws_close():
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


def _run_loop(node, stop_after):
    state = {"count": 0}

    async def broadcast(msg_type, payload):
        state["count"] += 1
        if state["count"] >= stop_after:
            node._running = False

    node.p2p.broadcast = broadcast

    async def run():
        await asyncio.wait_for(node._ping_loop(), timeout=5)

    asyncio.run(run())
    return state["count"]


def test_outstanding_ping_timestamp_not_refreshed():
    t0 = time.monotonic()
    answered = _make_peer("answered")
    answered.last_ping_at = t0 - 10
    answered.last_pong_at = t0 - 9
    stalled = _make_peer("stalled")
    stalled.last_ping_at = t0 - 10
    stalled.last_pong_at = t0 - 20

    node = _make_node(
        {"answered": answered, "stalled": stalled},
        pong_timeout=10.0,
        ping_interval=0.01,
    )
    _run_loop(node, stop_after=3)

    assert stalled.last_ping_at == t0 - 10
    assert answered.last_ping_at >= t0


def test_pong_timeout_fires_even_when_ping_interval_is_short():
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
    _run_loop(node, stop_after=30)

    assert peer.closed is True
    assert timeout_calls
