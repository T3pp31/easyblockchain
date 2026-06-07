import asyncio

import pytest

from useful_blockchain.network.node import Node


def _pow_overrides(port: int, bootstrap: list[str] | None = None) -> dict:
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
            "peer_connect": {"allow_private_ips": True},
        },
        "node": {"data_dir": f"/tmp/ebc-test-{port}"},
    }


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_two_node_pow_sync():
    node1 = Node(overrides=_pow_overrides(0))
    await node1.start()
    port1 = node1.p2p._actual_port
    url1 = f"ws://127.0.0.1:{port1}"

    node2 = Node(overrides=_pow_overrides(0, bootstrap=[url1]))
    await node2.start()

    await node1.add_block(["alice"], ["bob"])
    await asyncio.sleep(0.5)
    await node2.sync_chain()
    await asyncio.sleep(0.5)

    assert node1.chain_height >= 1
    assert node2.chain_height >= 1

    await node2.stop()
    await node1.stop()
