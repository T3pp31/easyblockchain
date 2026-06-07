"""ノード永続化の統合テスト。"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from useful_blockchain.network.node import Node
from useful_blockchain.persistence import ChainStore


def _pow_overrides(data_dir: Path) -> dict:
    return {
        "consensus": {
            "type": "pow",
            "pow": {"initial_difficulty": 1, "max_mining_iterations": 200000},
        },
        "network": {
            "host": "127.0.0.1",
            "port": 0,
            "bootstrap_peers": [],
            "ping_interval_seconds": 60,
        },
        "node": {"data_dir": str(data_dir)},
    }


def _pos_overrides(data_dir: Path, node_id: str) -> dict:
    return {
        "consensus": {"type": "pos", "pos": {"min_stake": 100, "block_reward": 10}},
        "network": {
            "host": "127.0.0.1",
            "port": 0,
            "bootstrap_peers": [],
            "ping_interval_seconds": 60,
        },
        "node": {"data_dir": str(data_dir), "node_id": node_id},
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pow_node_restarts_with_persisted_chain(tmp_path: Path) -> None:
    # Given: PoW ノードがブロックを追加して停止
    # When: 同一 data_dir で新しい Node を起動
    # Then: チェーン高さと内容が復元される
    data_dir = tmp_path / f"pow-{uuid.uuid4().hex}"
    node1 = Node(overrides=_pow_overrides(data_dir))
    await node1.start()
    await node1.add_block(["alice"], ["bob"])
    height = node1.chain_height
    chain_snapshot = list(node1.blockchain.chain)
    node_id = node1.node_id
    await node1.stop()

    node2 = Node(overrides=_pow_overrides(data_dir))
    assert node2.chain_height == height
    assert node2.blockchain.chain == chain_snapshot
    assert node2.node_id == node_id


@pytest.mark.integration
def test_pos_node_restarts_with_persisted_key_and_node_id(tmp_path: Path) -> None:
    # Given: PoS ノードが初回起動して永続化
    # When: 同一 data_dir で再起動
    # Then: node_id と署名鍵が維持される
    data_dir = tmp_path / f"pos-{uuid.uuid4().hex}"
    node_id = "validator-persist-1"
    stakes = {node_id: 200, "validator-b": 300}

    node1 = Node(
        overrides=_pos_overrides(data_dir, node_id),
        genesis_stakes=stakes,
    )
    public_key_1 = node1.signature_manager.export_public_key()
    assert node1.node_id == node_id

    node2 = Node(
        overrides=_pos_overrides(data_dir, node_id),
        genesis_stakes=stakes,
    )
    public_key_2 = node2.signature_manager.export_public_key()
    assert node2.node_id == node_id
    assert public_key_1 == public_key_2

    store = ChainStore(node2.settings.persistence)
    loaded = store.load(data_dir)
    assert loaded is not None
    assert loaded.genesis_stakes == stakes


@pytest.mark.integration
def test_pos_genesis_stakes_loaded_from_disk_overrides_constructor(
    tmp_path: Path,
) -> None:
    # Given: ディスクに保存済みの genesis_stakes
    # When: 異なるコンストラクタ引数で再起動
    # Then: ディスク上の stakes が優先される
    data_dir = tmp_path / f"pos-stakes-{uuid.uuid4().hex}"
    node_id = "validator-stakes-1"
    original_stakes = {node_id: 200}

    Node(
        overrides=_pos_overrides(data_dir, node_id),
        genesis_stakes=original_stakes,
    )

    node2 = Node(
        overrides=_pos_overrides(data_dir, node_id),
        genesis_stakes={"other": 999},
    )
    assert node2.genesis_stakes == original_stakes
