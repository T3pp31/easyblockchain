"""ハッシュ計算ユーティリティ。"""

from __future__ import annotations

import hashlib
import json

from useful_blockchain.types import Block, TransactionBody


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def calc_body_hash(transaction: TransactionBody) -> str:
    tran_string = json.dumps(transaction, sort_keys=True).encode()
    return sha256_hex(str(tran_string))


def calc_legacy_tran_hash(prev_hash: str, body_hash: str) -> str:
    return sha256_hex(prev_hash + body_hash)


def calc_pow_tran_hash(prev_hash: str, body_hash: str, nonce: int) -> str:
    return sha256_hex(prev_hash + body_hash + str(nonce))


def calc_pos_tran_hash(prev_hash: str, body_hash: str, validator_id: str, slot: int) -> str:
    return sha256_hex(prev_hash + body_hash + validator_id + str(slot))


def meets_difficulty(hash_hex: str, difficulty: int) -> bool:
    """difficulty は先頭の 16 進ゼロ文字数。"""
    if difficulty <= 0:
        return True
    return hash_hex.startswith("0" * difficulty)


def genesis_hash(chain: list[Block]) -> str:
    if not chain:
        return "0" * 64
    first_header = chain[0].get("block_header", {})
    return str(first_header.get("prev_hash", "0" * 64))
