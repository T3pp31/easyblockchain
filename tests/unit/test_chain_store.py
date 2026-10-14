"""ChainStore のユニットテスト。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from useful_blockchain.persistence import ChainStore, ChainStoreError, PersistedState
from useful_blockchain.settings import parse_settings
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


def test_save_fsyncs_each_written_file_before_replace(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: fsync / os.replace 呼び出しを記録するモンキーパッチ
    # When: save する
    # Then: 各ファイルの fsync が replace の前に行われ、
    #       リネーム完了後にディレクトリ fsync が 1 回呼ばれる
    events: list[str] = []
    real_fsync = os.fsync

    def fake_fsync(fd: int) -> None:
        events.append("fsync")
        real_fsync(fd)

    def fake_replace(src: object, dst: object) -> None:
        events.append(f"replace:{dst}")

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(os, "fsync", fake_fsync)
        monkeypatch.setattr(os, "replace", fake_replace)
        store.save(data_dir, sample_state)
    finally:
        monkeypatch.undo()

    # fsync 4 回（chain/meta/genesis_stakes の 3 回 + ディレクトリ 1 回）と replace 3 回
    assert sum(event == "fsync" for event in events) == 4
    replaced = {
        event.split("replace:", 1)[1]
        for event in events
        if event.startswith("replace:")
    }
    assert replaced == {
        str(data_dir / "chain.json"),
        str(data_dir / "meta.json"),
        str(data_dir / "genesis_stakes.json"),
    }
    # 全リネームの後、最後にディレクトリ fsync が 1 回行われる
    assert events[-1] == "fsync"
    replace_indexes = [
        index for index, event in enumerate(events) if event.startswith("replace:")
    ]
    assert all(index < len(events) - 1 for index in replace_indexes)


def test_save_raises_and_removes_tmp_when_fsync_fails(
    store: ChainStore, data_dir: Path, sample_state: PersistedState, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: fsync が OSError を送出する環境
    # When: save する
    # Then: ChainStoreError となり tmp ファイルは削除される

    def broken_fsync(fd: int) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr(os, "fsync", broken_fsync)
    with pytest.raises(ChainStoreError, match="Failed to write"):
        store.save(data_dir, sample_state)
    assert not list(data_dir.glob("*.tmp"))
    assert not (data_dir / "chain.json").exists()


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


def test_save_creates_keys_dir_with_restricted_permissions(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: p2p 秘密鍵付き状態
    # When: save する
    # Then: keys ディレクトリのパーミッションが 0700
    sample_state.p2p_identity_pem = b"-----BEGIN PRIVATE KEY-----\nidentity\n-----END PRIVATE KEY-----\n"
    store.save(data_dir, sample_state)
    keys_dir = data_dir / "keys"
    assert keys_dir.is_dir()
    assert oct(keys_dir.stat().st_mode & 0o777) == oct(0o700)


def test_save_tightens_existing_keys_dir_permissions(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: 緩い権限で作成済みの keys ディレクトリ
    keys_dir = data_dir / "keys"
    keys_dir.mkdir(parents=True)
    os.chmod(keys_dir, 0o755)
    sample_state.private_key_pem = b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n"
    # When: save する
    # Then: keys ディレクトリのパーミッションが 0700 に締め直される
    store.save(data_dir, sample_state)
    assert oct(keys_dir.stat().st_mode & 0o777) == oct(0o700)


def test_save_succeeds_with_stale_tmp_file(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: クラッシュ等で残存した一時ファイル
    keys_dir = data_dir / "keys"
    keys_dir.mkdir(parents=True)
    (keys_dir / "node.pem.tmp").write_bytes(b"stale")
    sample_state.private_key_pem = b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n"
    # When: save する
    # Then: 残存一時ファイルを置き換えて保存に成功する
    store.save(data_dir, sample_state)
    key_path = keys_dir / "node.pem"
    assert key_path.exists()
    assert not (keys_dir / "node.pem.tmp").exists()


def test_write_bytes_atomic_writes_all_bytes_on_short_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: os.write が 1 回の呼び出しで 1 バイトしか書き込めない環境
    data = b"0123456789"
    path = tmp_path / "out.bin"
    real_write = os.write

    def one_byte_write(fd: int, payload: memoryview) -> int:
        if not payload:
            return 0
        real_write(fd, payload[:1])
        return 1

    monkeypatch.setattr(os, "write", one_byte_write)
    # When: アトミック書き込みを行う
    # Then: 短書き込みが発生しても全バイトが書き込まれる
    ChainStore._write_bytes_atomic(path, data, mode=0o600)
    assert path.read_bytes() == data


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


def test_save_raises_when_chain_file_escapes_data_dir(
    data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: data_dir 外へエスケープする chain_file 設定
    # When: save を呼ぶ
    # Then: ChainStoreError が発生する
    store = ChainStore(PersistenceSettings(chain_file="../../escape.json"))
    with pytest.raises(ChainStoreError, match="outside data_dir"):
        store.save(data_dir, sample_state)


def test_save_raises_when_keys_dir_escapes_data_dir(
    data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: data_dir 外へエスケープする keys_dir 設定
    # When: 秘密鍵付きで save を呼ぶ
    # Then: ChainStoreError が発生する
    sample_state.private_key_pem = b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n"
    store = ChainStore(PersistenceSettings(keys_dir="../escape-keys"))
    with pytest.raises(ChainStoreError, match="outside data_dir"):
        store.save(data_dir, sample_state)


def test_load_succeeds_when_chain_file_at_size_limit(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: chain.json が上限ちょうどのサイズ
    # When: load を呼ぶ
    # Then: 正常に読み込める
    store.save(data_dir, sample_state)
    chain_path = data_dir / "chain.json"
    actual_size = chain_path.stat().st_size
    store_at_limit = ChainStore(PersistenceSettings(max_chain_file_bytes=actual_size))
    loaded = store_at_limit.load(data_dir)
    assert loaded is not None
    assert loaded.chain == sample_state.chain


def test_load_raises_when_chain_file_exceeds_size_limit(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: chain.json が上限を1バイト超過
    # When: load を呼ぶ
    # Then: ChainStoreError が発生する
    store.save(data_dir, sample_state)
    chain_path = data_dir / "chain.json"
    actual_size = chain_path.stat().st_size
    store_strict = ChainStore(PersistenceSettings(max_chain_file_bytes=actual_size - 1))
    with pytest.raises(ChainStoreError, match="Chain file too large"):
        store_strict.load(data_dir)


def test_parse_settings_reads_max_chain_file_bytes() -> None:
    # Given: max_chain_file_bytes を含む設定
    # When: parse_settings を呼ぶ
    # Then: 値が反映される
    settings = parse_settings({"persistence": {"max_chain_file_bytes": 1048576}})
    assert settings.persistence.max_chain_file_bytes == 1048576


def test_save_skips_keys_when_store_keys_on_disk_false(
    data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: store_keys_on_disk=false
    # When: 秘密鍵付き状態を save する
    # Then: 鍵ファイルは作成されない
    sample_state.private_key_pem = b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n"
    sample_state.p2p_identity_pem = b"-----BEGIN PRIVATE KEY-----\np2p\n-----END PRIVATE KEY-----\n"
    store = ChainStore(PersistenceSettings(store_keys_on_disk=False))
    store.save(data_dir, sample_state)
    assert not (data_dir / "keys" / "node.pem").exists()
    assert not (data_dir / "keys" / "p2p_identity.pem").exists()
    assert (data_dir / "chain.json").exists()


def test_load_skips_keys_when_store_keys_on_disk_false(
    data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: 鍵ファイルが存在するが store_keys_on_disk=false
    # When: load する
    # Then: 鍵は読み込まれない
    sample_state.private_key_pem = b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n"
    sample_state.p2p_identity_pem = b"-----BEGIN PRIVATE KEY-----\np2p\n-----END PRIVATE KEY-----\n"
    write_store = ChainStore(PersistenceSettings(store_keys_on_disk=True))
    write_store.save(data_dir, sample_state)
    read_store = ChainStore(PersistenceSettings(store_keys_on_disk=False))
    loaded = read_store.load(data_dir)
    assert loaded is not None
    assert loaded.private_key_pem is None
    assert loaded.p2p_identity_pem is None


def test_load_raises_chain_store_error_when_meta_is_not_dict(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: JSON 配列の meta.json
    # When: load する
    # Then: ChainStoreError が発生する
    store.save(data_dir, sample_state)
    (data_dir / "meta.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ChainStoreError, match="must contain a JSON object"):
        store.load(data_dir)


def test_load_raises_chain_store_error_when_schema_version_not_numeric(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: schema_version が数値変換不能な meta.json
    # When: load する
    # Then: ChainStoreError が発生する
    store.save(data_dir, sample_state)
    meta_path = data_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["schema_version"] = "not-a-number"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ChainStoreError, match="Invalid schema_version"):
        store.load(data_dir)


def test_load_raises_chain_store_error_when_stake_value_not_numeric(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: 数値変換不能な stake 値を含む genesis_stakes.json
    # When: load する
    # Then: ChainStoreError が発生する
    store.save(data_dir, sample_state)
    stakes_path = data_dir / "genesis_stakes.json"
    stakes_path.write_text(
        json.dumps({"validator-a": "not-a-number"}), encoding="utf-8"
    )
    with pytest.raises(ChainStoreError, match="Invalid stake value"):
        store.load(data_dir)


def test_load_raises_chain_store_error_when_schema_version_is_infinite(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: schema_version が Infinity に解決される meta.json
    # When: load する
    # Then: OverflowError も ChainStoreError に統一される
    store.save(data_dir, sample_state)
    (data_dir / "meta.json").write_text('{"schema_version": 1e999}', encoding="utf-8")
    with pytest.raises(ChainStoreError, match="Invalid schema_version"):
        store.load(data_dir)


def test_load_raises_chain_store_error_when_stake_value_is_infinite(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: Infinity に解決される stake 値を含む genesis_stakes.json
    # When: load する
    # Then: 原因キーを含む ChainStoreError が発生する
    store.save(data_dir, sample_state)
    (data_dir / "genesis_stakes.json").write_text(
        '{"validator-a": 1e999}', encoding="utf-8"
    )
    with pytest.raises(
        ChainStoreError, match="Invalid stake value for 'validator-a'"
    ):
        store.load(data_dir)


def test_load_raises_chain_store_error_on_invalid_utf8(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: 不正な UTF-8 バイト列を含む chain.json
    # When: load する
    # Then: ChainStoreError が発生する
    store.save(data_dir, sample_state)
    (data_dir / "chain.json").write_bytes(b'[\x80\x81{"broken')
    with pytest.raises(ChainStoreError, match="Invalid JSON"):
        store.load(data_dir)


def test_load_raises_chain_store_error_when_key_file_read_fails(
    store: ChainStore, data_dir: Path, sample_state: PersistedState
) -> None:
    # Given: 鍵パスがディレクトリで読み込みに失敗する状態
    # When: load する
    # Then: ChainStoreError が発生する
    sample_state.private_key_pem = (
        b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n"
    )
    store.save(data_dir, sample_state)
    key_path = data_dir / "keys" / "node.pem"
    key_path.unlink()
    key_path.mkdir()
    with pytest.raises(ChainStoreError, match="Failed to read"):
        store.load(data_dir)
