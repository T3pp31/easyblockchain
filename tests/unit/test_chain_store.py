"""ChainStore のユニットテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from useful_blockchain.persistence import ChainStore, ChainStoreError, PersistedState
from useful_blockchain.types import DEFAULT_GENESIS_PREV_HASH, PersistenceSettings


@pytest.fixture
def persistence_settings() -> PersistenceSettings:
    return PersistenceSettings()


@pytest.fixture
def store(persistence_settings: PersistenceSettings) -> ChainStore:
    return ChainStore(persistence_settings)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "node-data"


@pytest.fixture
def sample_state() -> PersistedState:
    return PersistedState(
        chain=[
            {
                "block_index": 1,
                "block_item": "2024-01-01 00:00:00",
                "block_header": {
                    "prev_hash": DEFAULT_GENESIS_PREV_HASH,
                    "tran_hash": "a" * 64,
                },
                "tran_counter": 2,
                "tran_body": {"input_data": ["x"], "output_data": ["y"]},
            }
        ],
        node_id="test-node-1",
        genesis_prev_hash=DEFAULT_GENESIS_PREV_HASH,
        genesis_stakes={"validator-a": 100},
        private_key_pem=None,
    )


def test_load_returns_none_when_meta_missing(store: ChainStore, data_dir: Path) -> None:
    # Given: 空の data_dir
    # When: load を呼ぶ
    # Then: None が返る
    assert store.load(data_dir) is None


def test_save_and_load_roundtrip(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: 永続化状態
    # When: save 後に load する
    # Then: 内容が一致する
    store.save(data_dir, sample_state)
    loaded = store.load(data_dir)
    assert loaded is not None
    assert loaded.chain == sample_state.chain
    assert loaded.node_id == sample_state.node_id
    assert loaded.genesis_prev_hash == sample_state.genesis_prev_hash
    assert loaded.genesis_stakes == sample_state.genesis_stakes


def test_save_and_load_empty_chain(store: ChainStore, data_dir: Path) -> None:
    # Given: 空チェーンの状態
    # When: save 後に load する
    # Then: 空チェーンが復元される
    state = PersistedState(
        chain=[],
        node_id="empty-node",
        genesis_prev_hash=DEFAULT_GENESIS_PREV_HASH,
        genesis_stakes={},
    )
    store.save(data_dir, state)
    loaded = store.load(data_dir)
    assert loaded is not None
    assert loaded.chain == []


def test_save_writes_private_key_with_restricted_permissions(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: 秘密鍵付き状態
    # When: save する
    # Then: 鍵ファイルのパーミッションが 0600
    sample_state.private_key_pem = b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n"
    store.save(data_dir, sample_state)
    key_path = data_dir / "keys" / "node.pem"
    assert key_path.exists()
    assert oct(key_path.stat().st_mode & 0o777) == oct(0o600)


def test_load_raises_on_invalid_json(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: 破損した chain.json
    # When: load する
    # Then: ChainStoreError が発生する
    store.save(data_dir, sample_state)
    chain_path = data_dir / "chain.json"
    chain_path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(ChainStoreError, match="Invalid JSON"):
        store.load(data_dir)


def test_load_raises_on_checksum_mismatch(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: checksum と不一致の chain.json
    # When: load する
    # Then: ChainStoreError が発生する
    store.save(data_dir, sample_state)
    chain_path = data_dir / "chain.json"
    chain_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ChainStoreError, match="checksum mismatch"):
        store.load(data_dir)


def test_load_raises_on_unsupported_schema_version(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: 未対応の schema_version
    # When: load する
    # Then: ChainStoreError が発生する
    store.save(data_dir, sample_state)
    meta_path = data_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["schema_version"] = 999
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ChainStoreError, match="Unsupported schema version"):
        store.load(data_dir)


def test_load_raises_when_chain_file_missing(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: meta のみ存在
    # When: load する
    # Then: ChainStoreError が発生する
    store.save(data_dir, sample_state)
    (data_dir / "chain.json").unlink()
    with pytest.raises(ChainStoreError, match="Missing chain file"):
        store.load(data_dir)


def test_exists_returns_true_after_save(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: 未保存の data_dir
    # When: save 後に exists を確認
    # Then: True になる
    assert store.exists(data_dir) is False
    store.save(data_dir, sample_state)
    assert store.exists(data_dir) is True
