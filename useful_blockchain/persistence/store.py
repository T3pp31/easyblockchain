"""data_dir へのチェーン永続化。"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from useful_blockchain.types import Block, PersistenceSettings


class ChainStoreError(Exception):
    """永続化ストアの読み書きエラー。"""


@dataclass
class PersistedState:
    chain: list[Block]
    node_id: str
    genesis_prev_hash: str
    genesis_stakes: dict[str, int]
    private_key_pem: bytes | None = None
    p2p_identity_pem: bytes | None = None


class ChainStore:
    """チェーンと関連メタデータのファイル I/O。"""

    def __init__(self, settings: PersistenceSettings) -> None:
        self._settings = settings

    @staticmethod
    def _safe_child_path(data_dir: Path, *parts: str) -> Path:
        root = data_dir.expanduser().resolve(strict=False)
        target = root.joinpath(*parts).resolve(strict=False)
        if not target.is_relative_to(root):
            raise ChainStoreError(
                f"Refusing path outside data_dir: {target} (base={root})"
            )
        return target

    def _meta_path(self, data_dir: Path) -> Path:
        return self._safe_child_path(data_dir, self._settings.meta_file)

    def _chain_path(self, data_dir: Path) -> Path:
        return self._safe_child_path(data_dir, self._settings.chain_file)

    def _genesis_stakes_path(self, data_dir: Path) -> Path:
        return self._safe_child_path(data_dir, self._settings.genesis_stakes_file)

    def _private_key_path(self, data_dir: Path) -> Path:
        return self._safe_child_path(
            data_dir,
            self._settings.keys_dir,
            self._settings.private_key_file,
        )

    def _p2p_identity_path(self, data_dir: Path) -> Path:
        return self._safe_child_path(
            data_dir,
            self._settings.keys_dir,
            self._settings.p2p_identity_file,
        )

    def exists(self, data_dir: Path) -> bool:
        return self._meta_path(data_dir).exists()

    def load(self, data_dir: Path) -> PersistedState | None:
        meta_path = self._meta_path(data_dir)
        if not meta_path.exists():
            return None

        meta = self._read_json(meta_path)
        schema_version = int(meta.get("schema_version", 0))
        if schema_version != self._settings.schema_version:
            raise ChainStoreError(
                f"Unsupported schema version: {schema_version} "
                f"(expected {self._settings.schema_version})"
            )

        chain_path = self._chain_path(data_dir)
        if not chain_path.exists():
            raise ChainStoreError(f"Missing chain file: {chain_path}")

        self._assert_file_size_within_limit(
            chain_path, self._settings.max_chain_file_bytes
        )
        chain_data = self._read_json(chain_path)
        if not isinstance(chain_data, list):
            raise ChainStoreError("chain file must contain a JSON array")

        stored_checksum = meta.get("chain_checksum")
        if stored_checksum is not None:
            actual_checksum = self._compute_checksum(chain_data)
            if stored_checksum != actual_checksum:
                raise ChainStoreError("Chain checksum mismatch: file may be corrupted")

        genesis_stakes: dict[str, int] = {}
        stakes_path = self._genesis_stakes_path(data_dir)
        if stakes_path.exists():
            stakes_data = self._read_json(stakes_path)
            if not isinstance(stakes_data, dict):
                raise ChainStoreError("genesis_stakes file must contain a JSON object")
            genesis_stakes = {str(k): int(v) for k, v in stakes_data.items()}

        private_key_pem: bytes | None = None
        p2p_identity_pem: bytes | None = None
        if self._settings.store_keys_on_disk:
            key_path = self._private_key_path(data_dir)
            if key_path.exists():
                private_key_pem = key_path.read_bytes()

            identity_path = self._p2p_identity_path(data_dir)
            if identity_path.exists():
                p2p_identity_pem = identity_path.read_bytes()

        node_id = str(meta.get("node_id", ""))
        genesis_prev_hash = str(meta.get("genesis_prev_hash", ""))

        return PersistedState(
            chain=chain_data,
            node_id=node_id,
            genesis_prev_hash=genesis_prev_hash,
            genesis_stakes=genesis_stakes,
            private_key_pem=private_key_pem,
            p2p_identity_pem=p2p_identity_pem,
        )

    def save(self, data_dir: Path, state: PersistedState) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)

        chain_checksum = self._compute_checksum(state.chain)
        meta: dict[str, Any] = {
            "schema_version": self._settings.schema_version,
            "node_id": state.node_id,
            "genesis_prev_hash": state.genesis_prev_hash,
            "chain_checksum": chain_checksum,
        }

        self._write_json_atomic(self._chain_path(data_dir), state.chain)
        self._write_json_atomic(self._meta_path(data_dir), meta)
        self._write_json_atomic(
            self._genesis_stakes_path(data_dir), state.genesis_stakes
        )

        if self._settings.store_keys_on_disk:
            keys_dir = self._safe_child_path(data_dir, self._settings.keys_dir)
            if state.private_key_pem is not None or state.p2p_identity_pem is not None:
                keys_dir.mkdir(parents=True, exist_ok=True)
            if state.private_key_pem is not None:
                key_path = self._private_key_path(data_dir)
                self._write_bytes_atomic(key_path, state.private_key_pem)
                os.chmod(key_path, 0o600)
            if state.p2p_identity_pem is not None:
                identity_path = self._p2p_identity_path(data_dir)
                self._write_bytes_atomic(identity_path, state.p2p_identity_pem)
                os.chmod(identity_path, 0o600)

    @staticmethod
    def _compute_checksum(chain: list[Block]) -> str:
        payload = json.dumps(chain, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _assert_file_size_within_limit(self, path: Path, max_bytes: int) -> None:
        if max_bytes <= 0:
            return
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise ChainStoreError(f"Failed to stat {path}: {exc}") from exc
        if size > max_bytes:
            raise ChainStoreError(
                f"Chain file too large: {path} is {size} bytes (max {max_bytes})"
            )

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            with path.open("r", encoding="utf-8") as fp:
                return json.load(fp)
        except json.JSONDecodeError as exc:
            raise ChainStoreError(f"Invalid JSON in {path}: {exc}") from exc
        except OSError as exc:
            raise ChainStoreError(f"Failed to read {path}: {exc}") from exc

    @staticmethod
    def _write_json_atomic(path: Path, data: Any) -> None:
        text = json.dumps(data, indent=2, ensure_ascii=False)
        ChainStore._write_bytes_atomic(path, text.encode("utf-8"))

    @staticmethod
    def _write_bytes_atomic(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp_path.write_bytes(data)
            os.replace(tmp_path, path)
        except OSError as exc:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise ChainStoreError(f"Failed to write {path}: {exc}") from exc
