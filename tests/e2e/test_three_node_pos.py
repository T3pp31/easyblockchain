import asyncio
import uuid

import pytest

from useful_blockchain.network.node import Node


GENESIS_STAKES = {
    "pos-node-0": 200,
    "pos-node-1": 200,
    "pos-node-2": 200,
}


def _pos_overrides(
    node_id: str, port: int, bootstrap: list[str], *, run_id: str
) -> dict:
    return {
        "consensus": {
            "type": "pos",
            "pos": {"min_stake": 100, "block_reward": 5},
        },
        "network": {
            "host": "127.0.0.1",
            "port": port,
            "bootstrap_peers": bootstrap,
            "ping_interval_seconds": 60,
        },
        "node": {
            "data_dir": f"/tmp/ebc-pos-{run_id}-{node_id}",
            "node_id": node_id,
        },
    }


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_three_node_pos_network():
    nodes: list[Node] = []
    urls: list[str] = []
    run_id = uuid.uuid4().hex

    for i in range(3):
        node_id = f"pos-node-{i}"
        node = Node(
            overrides=_pos_overrides(node_id, 0, urls.copy(), run_id=run_id),
            genesis_stakes=GENESIS_STAKES,
        )
        await node.start()
        nodes.append(node)
        urls.append(node.p2p.local_url)
        await asyncio.sleep(0.2)

    proposer_node = nodes[0]
    for node in nodes:
        slot1 = node.consensus.select_proposer(1)
        if slot1 == node.node_id:
            proposer_node = node
            break

    await proposer_node.add_block(["staker"], ["receiver"])
    await asyncio.sleep(0.5)

    for node in nodes:
        if node is not proposer_node:
            await node.sync_chain()
    await asyncio.sleep(0.5)

    assert proposer_node.chain_height >= 1

    for node in reversed(nodes):
        await node.stop()
