"""署名付き HELLO によるピア認証。"""

from __future__ import annotations

import logging
import time
from typing import Any

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric import rsa

from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import PeerAuthSettings

logger = logging.getLogger(__name__)


def hello_signing_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """HELLO 署名対象フィールドのみを返す。"""
    signing: dict[str, Any] = {
        "node_id": payload["node_id"],
        "consensus_type": payload["consensus_type"],
        "genesis_hash": payload["genesis_hash"],
        "timestamp": int(payload["timestamp"]),
    }
    if "advertised_url" in payload:
        signing["advertised_url"] = str(payload["advertised_url"])
    return signing


def build_hello_payload(
    node_id: str,
    consensus_type: str,
    chain_height: int,
    genesis_hash_value: str,
    signature_manager: SignatureManager,
    advertised_url: str | None = None,
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
    if advertised_url:
        base["advertised_url"] = advertised_url
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

    try:
        timestamp = int(payload["timestamp"])
    except (TypeError, ValueError, OverflowError):
        return False
    current = now if now is not None else time.time()
    if abs(current - timestamp) > settings.max_skew_seconds:
        return False

    try:
        signature = bytes.fromhex(str(payload["signature"]))
        public_key_pem = str(payload["public_key"]).encode("utf-8")
    except (ValueError, TypeError):
        return False

    sig_manager = SignatureManager()
    try:
        public_key = sig_manager.import_public_key(public_key_pem)
        if not isinstance(public_key, rsa.RSAPublicKey):
            # RSA 以外の鍵種は暗黙の TypeError 依存ではなく明示的に拒否する
            logger.debug("HELLO verification failed: public key is not RSA")
            return False
        signing_data = hello_signing_payload(payload)
        return sig_manager.verify_signature(signing_data, signature, public_key)
    except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
        logger.debug("HELLO verification failed: %r", exc)
        return False
