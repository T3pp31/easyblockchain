"""Node の秘密鍵注入・非永続化テスト。"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from useful_blockchain.network.node import Node
from useful_blockchain.signature import SignatureManager


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


def _generate_private_key_pem() -> bytes:
    manager = SignatureManager()
    manager.generate_key_pair()
    return manager.export_private_key()


def test_pos_node_persists_generated_validator_key(tmp_path: Path) -> None:
    # Given: 外部注入なしの PoS ノード
    # When: 初回起動する
    # Then: バリデータ鍵がディスクに保存される
    data_dir = tmp_path / f"pos-file-{uuid.uuid4().hex}"
    node_id = "validator-file"
    Node(overrides=_pos_overrides(data_dir, node_id), genesis_stakes={node_id: 200})
    key_path = data_dir / "keys" / "node.pem"
    assert key_path.exists()


def test_pos_node_external_validator_key_is_not_persisted(tmp_path: Path) -> None:
    # Given: コンストラクタでバリデータ鍵を注入
    # When: 初回起動する
    # Then: node.pem は作成されない
    data_dir = tmp_path / f"pos-external-{uuid.uuid4().hex}"
    node_id = "validator-external"
    validator_pem = _generate_private_key_pem()
    node = Node(
        overrides=_pos_overrides(data_dir, node_id),
        genesis_stakes={node_id: 200},
        validator_private_key_pem=validator_pem,
    )
    assert node.signature_manager.export_private_key() == validator_pem
    assert not (data_dir / "keys" / "node.pem").exists()


def test_pos_node_env_validator_key_is_not_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: 環境変数でバリデータ鍵を注入
    # When: 初回起動する
    # Then: node.pem は作成されない
    data_dir = tmp_path / f"pos-env-{uuid.uuid4().hex}"
    node_id = "validator-env"
    validator_pem = _generate_private_key_pem()
    monkeypatch.setenv(
        "EASYBLOCKCHAIN_VALIDATOR_PRIVATE_KEY",
        validator_pem.decode("utf-8"),
    )
    node = Node(
        overrides=_pos_overrides(data_dir, node_id),
        genesis_stakes={node_id: 200},
    )
    assert node.signature_manager.export_private_key() == validator_pem
    assert not (data_dir / "keys" / "node.pem").exists()


def test_constructor_validator_key_takes_priority_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: コンストラクタと env の両方に鍵がある
    # When: Node を起動する
    # Then: コンストラクタの鍵が使われる
    data_dir = tmp_path / f"pos-priority-{uuid.uuid4().hex}"
    node_id = "validator-priority"
    constructor_pem = _generate_private_key_pem()
    env_pem = _generate_private_key_pem()
    monkeypatch.setenv(
        "EASYBLOCKCHAIN_VALIDATOR_PRIVATE_KEY",
        env_pem.decode("utf-8"),
    )
    node = Node(
        overrides=_pos_overrides(data_dir, node_id),
        genesis_stakes={node_id: 200},
        validator_private_key_pem=constructor_pem,
    )
    assert node.signature_manager.export_private_key() == constructor_pem
