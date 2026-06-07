import asyncio

import pytest

from useful_blockchain.network.node import Node
from useful_blockchain.types import DEFAULT_GENESIS_PREV_HASH


def _pow_overrides(port: int, bootstrap: list[str] | None = None, genesis_prev_hash: str | None = None) -> dict:
    overrides: dict = {
        "consensus": {
            "type": "pow",
            "pow": {"initial_difficulty": 1, "max_mining_iterations": 200000},
        },
        "network": {
            "host": "127.0.0.1",
            "port": port,
            "bootstrap_peers": bootstrap or [],
            "ping_interval_seconds": 60,
        },
        "node": {"data_dir": f"/tmp/ebc-genesis-test-{port}"},
    }
    if genesis_prev_hash is not None:
        overrides["genesis"] = {"prev_hash": genesis_prev_hash}
    return overrides


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_same_genesis_nodes_connect_and_sync():
    # Given: 同一 genesis の2ノード
    # When: 接続してブロックを同期
    # Then: 両方が同じチェーン高さになる
    node1 = Node(overrides=_pow_overrides(0))
    await node1.start()
    port1 = node1.p2p._actual_port
    url1 = f"ws://127.0.0.1:{port1}"

    node2 = Node(overrides=_pow_overrides(0, bootstrap=[url1]))
    await node2.start()
    await asyncio.sleep(0.3)

    assert len(node1.p2p.peers) >= 1 or len(node2.p2p.peers) >= 1

    await node1.add_block(["alice"], ["bob"])
    await asyncio.sleep(0.5)
    await node2.sync_chain()
    await asyncio.sleep(0.5)

    assert node1.chain_height >= 1
    assert node2.chain_height >= 1

    await node2.stop()
    await node1.stop()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_different_genesis_nodes_disconnect():
    # Given: 異なる genesis prev_hash の2ノード
    # When: node2 が node1 に接続
    # Then: HELLO 後にピア接続が切断される
    alt_genesis = "1" * 64
    assert alt_genesis != DEFAULT_GENESIS_PREV_HASH

    node1 = Node(overrides=_pow_overrides(0))
    await node1.start()
    port1 = node1.p2p._actual_port
    url1 = f"ws://127.0.0.1:{port1}"

    node2 = Node(overrides=_pow_overrides(0, bootstrap=[url1], genesis_prev_hash=alt_genesis))
    await node2.start()
    await asyncio.sleep(0.5)

    for peer in list(node1.p2p.peers.values()):
        assert peer.closed is True

    await node2.stop()
    await node1.stop()
