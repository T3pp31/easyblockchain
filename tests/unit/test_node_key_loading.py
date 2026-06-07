"""Node の秘密鍵注入・非永続化テスト。"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from useful_blockchain.network.node import (
    Node,
    _P2P_IDENTITY_KEY_ENV,
    _VALIDATOR_PRIVATE_KEY_ENV,
)
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
        p2p_identity_key_pem=_generate_private_key_pem(),
    )
    assert node.signature_manager.export_private_key() == constructor_pem


def _pow_overrides(data_dir: Path) -> dict:
    return {
        "consensus": {"type": "pow"},
        "network": {
            "host": "127.0.0.1",
            "port": 0,
            "bootstrap_peers": [],
            "ping_interval_seconds": 60,
        },
        "node": {"data_dir": str(data_dir)},
    }


def test_production_require_external_keys_without_keys_raises(
    tmp_path: Path,
) -> None:
    # Given: require_external_keys=true で鍵未提供
    # When: Node を起動する
    # Then: ValueError が発生する
    data_dir = tmp_path / f"prod-no-keys-{uuid.uuid4().hex}"
    overrides = _pow_overrides(data_dir)
    overrides["node"]["require_external_keys"] = True
    with pytest.raises(ValueError, match="P2P identity key"):
        Node(overrides=overrides)


def test_production_with_file_env_keys_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: require_external_keys=true とファイル経由の鍵
    # When: Node を起動する
    # Then: 正常に初期化される
    data_dir = tmp_path / f"prod-file-keys-{uuid.uuid4().hex}"
    p2p_pem = _generate_private_key_pem()
    key_file = tmp_path / "p2p_identity.pem"
    key_file.write_bytes(p2p_pem)
    os.chmod(key_file, 0o600)
    monkeypatch.setenv("EASYBLOCKCHAIN_P2P_IDENTITY_KEY_FILE", str(key_file))
    overrides = _pow_overrides(data_dir)
    overrides["node"]["require_external_keys"] = True
    node = Node(overrides=overrides)
    assert node.p2p_identity_manager.export_private_key() == p2p_pem


def test_store_keys_on_disk_false_does_not_write_keys(tmp_path: Path) -> None:
    # Given: store_keys_on_disk=false
    # When: PoS ノードを起動する
    # Then: 鍵ファイルは作成されない
    data_dir = tmp_path / f"no-disk-keys-{uuid.uuid4().hex}"
    node_id = "validator-no-disk"
    overrides = _pos_overrides(data_dir, node_id)
    overrides["persistence"] = {"store_keys_on_disk": False}
    Node(overrides=overrides, genesis_stakes={node_id: 200})
    assert not (data_dir / "keys" / "node.pem").exists()
    assert not (data_dir / "keys" / "p2p_identity.pem").exists()


def test_pem_env_logs_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Given: PEM 環境変数で P2P 鍵を注入
    # When: Node を起動する
    # Then: process listing 警告がログに記録される
    import logging

    caplog.set_level(logging.WARNING)
    data_dir = tmp_path / f"pem-env-warn-{uuid.uuid4().hex}"
    p2p_pem = _generate_private_key_pem()
    monkeypatch.setenv(_P2P_IDENTITY_KEY_ENV, p2p_pem.decode("utf-8"))
    Node(overrides=_pow_overrides(data_dir))
    assert any("process listing" in record.message for record in caplog.records)


def test_production_pos_require_external_keys_without_validator_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: PoS + require_external_keys で P2P 鍵のみ提供
    # When: Node を起動する
    # Then: バリデータ鍵不足で ValueError
    data_dir = tmp_path / f"prod-pos-no-validator-{uuid.uuid4().hex}"
    node_id = "validator-missing"
    p2p_pem = _generate_private_key_pem()
    monkeypatch.setenv("EASYBLOCKCHAIN_P2P_IDENTITY_KEY_FILE", "")
    overrides = _pos_overrides(data_dir, node_id)
    overrides["node"]["require_external_keys"] = True
    with pytest.raises(ValueError, match="validator private key"):
        Node(
            overrides=overrides,
            genesis_stakes={node_id: 200},
            p2p_identity_key_pem=p2p_pem,
        )
