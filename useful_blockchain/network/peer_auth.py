"""署名付き HELLO によるピア認証。"""

from __future__ import annotations

import time
from typing import Any

from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import PeerAuthSettings


def hello_signing_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """HELLO 署名対象フィールドのみを返す。"""
    return {
        "node_id": payload["node_id"],
        "consensus_type": payload["consensus_type"],
        "genesis_hash": payload["genesis_hash"],
        "timestamp": int(payload["timestamp"]),
    }


def build_hello_payload(
    node_id: str,
    consensus_type: str,
    chain_height: int,
    genesis_hash_value: str,
    signature_manager: SignatureManager,
) -> dict[str, Any]:
    """署名付き HELLO ペイロードを構築する。"""
    timestamp = int(time.time())
    base = {
        "node_id": node_id,
        "consensus_type": consensus_type,
        "chain_height": chain_height,
        "genesis_hash": genesis_hash_value,
        "timestamp": timestamp,
    }
    signing_data = hello_signing_payload(base)
    signature = signature_manager.sign_data(signing_data)
    base["public_key"] = signature_manager.export_public_key().decode("utf-8")
    base["signature"] = signature.hex()
    return base


def verify_hello(
    payload: dict[str, Any],
    settings: PeerAuthSettings,
    now: float | None = None,
) -> bool:
    """HELLO ペイロードの署名とタイムスタンプを検証する。"""
    required = ("node_id", "consensus_type", "genesis_hash", "timestamp", "public_key", "signature")
    if not all(key in payload for key in required):
        return False

    timestamp = int(payload["timestamp"])
    current = now if now is not None else time.time()
    if abs(current - timestamp) > settings.max_skew_seconds:
        return False

    try:
        signature = bytes.fromhex(str(payload["signature"]))
        public_key_pem = str(payload["public_key"]).encode("utf-8")
    except (ValueError, TypeError):
        return False

    sig_manager = SignatureManager()
    public_key = sig_manager.import_public_key(public_key_pem)
    signing_data = hello_signing_payload(payload)
    return sig_manager.verify_signature(signing_data, signature, public_key)
