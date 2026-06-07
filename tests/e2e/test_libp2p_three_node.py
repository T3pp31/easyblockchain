"""libp2p + GossipSub トランスポートの E2E テスト。"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("libp2p")

from useful_blockchain.network.node import Node


def _libp2p_overrides(node_index: int, bootstrap: list[str]) -> dict:
    return {
        "consensus": {
            "type": "pow",
            "pow": {"initial_difficulty": 1, "max_mining_iterations": 200000},
        },
        "network": {
            "transport": "libp2p",
            "host": "127.0.0.1",
            "port": 0,
            "bootstrap_peers": [],
            "libp2p": {
                "listen_port": 0,
                "bootstrap_peers": bootstrap,
                "gossipsub_mesh_n": 3,
                "gossipsub_heartbeat_interval": 2.0,
            },
            "ping_interval_seconds": 60,
            "peer_auth": {"enabled": False},
        },
        "node": {
            "data_dir": f"/tmp/ebc-libp2p-{node_index}",
            "node_id": f"libp2p-node-{node_index}",
        },
    }


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_libp2p_three_node_pow_sync() -> None:
    # Given: libp2p トランスポートの3ノード
    # When: ブロックを生成しチェーン同期する
    # Then: 全ノードのチェーン高さが一致する
    nodes: list[Node] = []
    addrs: list[str] = []

    for i in range(3):
        node = Node(overrides=_libp2p_overrides(i, addrs.copy()))
        await node.start()
        nodes.append(node)
        addrs.append(node.transport.local_url)
        await asyncio.sleep(1.0)

    await nodes[0].add_block(["s1"], ["r1"])
    await asyncio.sleep(2.0)

    for node in nodes[1:]:
        await node.sync_chain()
    await asyncio.sleep(1.0)

    heights = [n.chain_height for n in nodes]
    assert max(heights) >= 1
    assert len(set(heights)) == 1

    for node in reversed(nodes):
        await asyncio.wait_for(node.stop(), timeout=10.0)
