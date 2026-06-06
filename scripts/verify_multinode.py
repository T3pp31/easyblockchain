#!/usr/bin/env python3
"""マルチノード動作確認スクリプト。"""

from __future__ import annotations

import asyncio
import sys


async def verify_pow_multinode() -> None:
    from useful_blockchain.network.node import Node

    nodes: list[Node] = []
    urls: list[str] = []

    print("=== PoW マルチノード検証 ===")
    for i in range(3):
        node = Node(
            overrides={
                "consensus": {
                    "type": "pow",
                    "pow": {"initial_difficulty": 1, "max_mining_iterations": 200000},
                },
                "network": {
                    "host": "127.0.0.1",
                    "port": 0,
                    "bootstrap_peers": urls.copy(),
                    "ping_interval_seconds": 60,
                },
                "node": {"data_dir": f"/tmp/ebc-verify-pow-{i}", "node_id": f"pow-{i}"},
            }
        )
        await node.start()
        nodes.append(node)
        urls.append(node.p2p.local_url)
        print(f"  Node {i} started: {node.p2p.local_url}")
        await asyncio.sleep(0.2)

    print("  Node0: block追加...")
    block = await nodes[0].add_block(["alice"], ["bob"])
    print(f"  Block #{block['block_index']} mined (hash prefix: {block['block_header']['tran_hash'][:8]}...)")
    await asyncio.sleep(0.5)

    print("  Node1, Node2: チェーン同期...")
    await nodes[1].sync_chain()
    await nodes[2].sync_chain()
    await asyncio.sleep(0.5)

    heights = [n.chain_height for n in nodes]
    print(f"  チェーン高さ: {heights}")
    if heights[0] < 1:
        raise SystemExit("FAIL: Node0 にブロックがありません")
    if heights[1] < 1 or heights[2] < 1:
        raise SystemExit(f"FAIL: 同期失敗 heights={heights}")

    hashes = [n.blockchain.chain[0]["block_header"]["tran_hash"] for n in nodes]
    if len(set(hashes)) != 1:
        raise SystemExit(f"FAIL: ブロックハッシュ不一致 {hashes}")
    print("  OK: 全ノードで同一ブロックを確認")

    await nodes[0].add_block(["carol"], ["dave"])
    await asyncio.sleep(0.5)
    await nodes[2].sync_chain()
    await asyncio.sleep(0.3)
    if nodes[2].chain_height < 2:
        raise SystemExit(f"FAIL: 2ブロック目の同期失敗 height={nodes[2].chain_height}")
    print(f"  OK: 2ブロック目まで同期 (heights={[n.chain_height for n in nodes]})")

    for node in reversed(nodes):
        await asyncio.wait_for(node.stop(), timeout=5.0)
    print("  PoW マルチノード検証: 成功\n")


async def verify_pos_multinode() -> None:
    from useful_blockchain.network.node import Node

    stakes = {"pos-0": 200, "pos-1": 200, "pos-2": 200}
    nodes: list[Node] = []
    urls: list[str] = []

    print("=== PoS マルチノード検証 ===")
    for i in range(3):
        node_id = f"pos-{i}"
        node = Node(
            overrides={
                "consensus": {"type": "pos", "pos": {"min_stake": 100}},
                "network": {
                    "host": "127.0.0.1",
                    "port": 0,
                    "bootstrap_peers": urls.copy(),
                    "ping_interval_seconds": 60,
                },
                "node": {"data_dir": f"/tmp/ebc-verify-pos-{i}", "node_id": node_id},
            },
            genesis_stakes=stakes,
        )
        await node.start()
        nodes.append(node)
        urls.append(node.p2p.local_url)
        print(f"  Node {node_id} started: {node.p2p.local_url}")
        await asyncio.sleep(0.2)

    proposer = nodes[0]
    for node in nodes:
        if node.consensus.select_proposer(1) == node.node_id:
            proposer = node
            break

    print(f"  Slot1 提案者: {proposer.node_id}")
    block = await proposer.add_block(["staker"], ["receiver"])
    print(f"  Block #{block['block_index']} proposed")
    await asyncio.sleep(0.5)

    for node in nodes:
        if node is not proposer:
            await node.sync_chain()
    await asyncio.sleep(0.3)

    heights = [n.chain_height for n in nodes]
    print(f"  チェーン高さ: {heights}")
    synced = [n for n in nodes if n.chain_height >= 1]
    if len(synced) < 2:
        raise SystemExit(f"FAIL: PoS 同期不足 heights={heights}")
    print("  OK: PoS マルチノードでブロック伝播を確認")

    for node in reversed(nodes):
        await asyncio.wait_for(node.stop(), timeout=5.0)
    print("  PoS マルチノード検証: 成功\n")


async def main() -> int:
    await verify_pow_multinode()
    await verify_pos_multinode()
    print("=== すべてのマルチノード検証が成功しました ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
