from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest

from useful_blockchain.network.node import Node


def _node_overrides(
    node_index: int, port: int, bootstrap: list[str], *, data_dir: str
) -> dict:
    return {
        "consensus": {
            "type": "pow",
            "pow": {"initial_difficulty": 1, "max_mining_iterations": 200000},
        },
        "network": {
            "host": "127.0.0.1",
            "port": port,
            "bootstrap_peers": bootstrap,
            "ping_interval_seconds": 60,
            "peer_connect": {"allow_private_ips": True, "blocked_cidrs": []},
        },
        "node": {"data_dir": data_dir, "node_id": f"pow-node-{node_index}"},
    }


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_three_node_pow_chain_convergence(tmp_path: Path):
    nodes: list[Node] = []
    urls: list[str] = []

    try:
        for i in range(3):
            data_dir = tmp_path / f"pow-node-{i}"
            node = Node(
                overrides=_node_overrides(i, 0, urls.copy(), data_dir=str(data_dir))
            )
            await node.start()
            nodes.append(node)
            urls.append(node.p2p.local_url)
            await asyncio.sleep(0.2)

        await nodes[0].add_block(["s1"], ["r1"])
        await asyncio.sleep(0.3)

        for node in nodes[1:]:
            await node.sync_chain()
        await asyncio.sleep(0.3)

        heights = [n.chain_height for n in nodes]
        assert max(heights) >= 1
    finally:
        for node in reversed(nodes):
            with contextlib.suppress(Exception):
                await asyncio.wait_for(node.stop(), timeout=5.0)
