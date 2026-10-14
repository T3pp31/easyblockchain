from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

import pytest

from useful_blockchain.network.node import Node


def _pow_overrides(
    port: int,
    bootstrap: list[str] | None = None,
    *,
    data_dir_suffix: str,
) -> dict:
    return {
        "consensus": {
            "type": "pow",
            "pow": {"initial_difficulty": 1, "max_mining_iterations": 200000},
        },
        "network": {
            "host": "127.0.0.1",
            "port": port,
            "bootstrap_peers": bootstrap or [],
            "ping_interval_seconds": 60,
            "peer_connect": {"allow_private_ips": True, "blocked_cidrs": []},
        },
        "node": {"data_dir": f"/tmp/ebc-test-{data_dir_suffix}"},
    }


async def _wait_until(
    predicate: Callable[[], bool], *, timeout: float = 10.0, message: str
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(message)
        await asyncio.sleep(0.05)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_two_node_pow_sync():
    run_id = uuid.uuid4().hex
    node1 = Node(overrides=_pow_overrides(0, data_dir_suffix=f"{run_id}-n1"))
    await node1.start()
    port1 = node1.p2p._actual_port
    url1 = f"ws://127.0.0.1:{port1}"

    node2 = Node(
        overrides=_pow_overrides(0, bootstrap=[url1], data_dir_suffix=f"{run_id}-n2")
    )
    await node2.start()

    await _wait_until(
        lambda: len(node2.p2p.peers) > 0,
        message="node2 がピアに接続できませんでした",
    )

    await node1.add_block(["alice"], ["bob"])
    await node2.sync_chain()
    await _wait_until(
        lambda: node2.chain_height >= 1,
        message="node2 がブロックを同期しませんでした",
    )

    assert node1.chain_height >= 1
    assert node2.chain_height >= 1

    await node2.stop()
    await node1.stop()
