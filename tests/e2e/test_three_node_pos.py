from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest

from useful_blockchain.network.node import Node

GENESIS_STAKES = {
    "pos-node-0": 200,
    "pos-node-1": 200,
    "pos-node-2": 200,
}


def _pos_overrides(
    node_id: str, port: int, bootstrap: list[str], *, data_dir: Path
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
            "peer_connect": {"allow_private_ips": True, "blocked_cidrs": []},
        },
        "node": {
            "data_dir": str(data_dir),
            "node_id": node_id,
        },
    }


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_three_node_pos_network(tmp_path: Path):
    nodes: list[Node] = []
    urls: list[str] = []

    try:
        for i in range(3):
            node_id = f"pos-node-{i}"
            node = Node(
                overrides=_pos_overrides(node_id, 0, urls.copy(), data_dir=tmp_path / node_id),
                genesis_stakes=GENESIS_STAKES,
            )
            nodes.append(node)
            await node.start()
            urls.append(node.p2p.local_url)
            await asyncio.sleep(0.2)

        # 各ノードが全バリデータの公開鍵を事前に信頼する PoS ネットワークを構成する。
        for node in nodes:
            for validator in nodes:
                node.consensus.register_validator(
                    validator.node_id,
                    GENESIS_STAKES[validator.node_id],
                    validator.signature_manager.export_public_key().decode("utf-8"),
                )

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
        # Given: proposer が生成したブロックと同期要求済みの全ノード
        # When: 全ノードのチェーンが一致するまで期限付きで待つ
        # Then: 高さだけでなくブロック内容も一致する
        async def wait_for_convergence():
            while any(node.blockchain.chain != proposer_node.blockchain.chain for node in nodes):
                await asyncio.sleep(0.05)

        await asyncio.wait_for(wait_for_convergence(), timeout=5.0)
        assert proposer_node.chain_height >= 1
        for node in nodes:
            assert node.chain_height == proposer_node.chain_height
            assert node.blockchain.chain == proposer_node.blockchain.chain
    finally:
        for node in reversed(nodes):
            with contextlib.suppress(Exception):
                await asyncio.wait_for(node.stop(), timeout=5.0)
