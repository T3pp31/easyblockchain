#!/usr/bin/env python3
"""ブロックチェーンノード起動 CLI。"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from useful_blockchain.network.node import Node


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run an easyblockchain P2P node")
    parser.add_argument("--config", help="Path to config YAML", default=None)
    parser.add_argument("--consensus", choices=["pow", "pos"], help="Consensus type override")
    parser.add_argument("--port", type=int, help="Network port override")
    parser.add_argument("--bootstrap", nargs="*", default=[], help="Bootstrap peer URLs")
    parser.add_argument("--add-block", nargs=2, metavar=("INPUT", "OUTPUT"), help="Add one block on start")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    overrides: dict = {}
    if args.consensus:
        overrides.setdefault("consensus", {})["type"] = args.consensus
    if args.port:
        overrides.setdefault("network", {})["port"] = args.port
    if args.bootstrap:
        overrides.setdefault("network", {})["bootstrap_peers"] = args.bootstrap

    node = Node(config_path=args.config, overrides=overrides or None)
    await node.start()
    print(f"Node {node.node_id} listening on {node.p2p.local_url} ({node.settings.consensus.type})")

    if args.add_block:
        block = await node.add_block(args.add_block[0], args.add_block[1])
        print(f"Added block #{block['block_index']}")

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("Shutting down...")
        await node.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
