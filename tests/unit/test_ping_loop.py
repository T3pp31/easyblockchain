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


def test_peer_that_never_ponged_is_disconnected_on_timeout():
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
    _run_loop(node, stop_after=3)

    assert peer.closed is True
    assert len(timeout_calls) == 1


def test_never_pinged_peer_is_not_disconnected():
    peer = _make_peer("fresh")

    node = _make_node({"fresh": peer}, pong_timeout=5.0, ping_interval=0.01)
    _run_loop(node, stop_after=3)

    assert peer.closed is False


def test_answered_peer_is_not_disconnected():
    peer = _make_peer("healthy")
    t0 = time.monotonic()
    peer.last_ping_at = t0 - 10
    peer.last_pong_at = t0 - 9

    node = _make_node({"healthy": peer}, pong_timeout=0.5, ping_interval=0.01)
    _run_loop(node, stop_after=3)

    assert peer.closed is False
