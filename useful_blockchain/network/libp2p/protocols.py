"""libp2p ストリームプロトコル用メッセージ codec。"""

from __future__ import annotations

import json
from typing import Any

from useful_blockchain.network.messages import MessageDecodeError, MessageType, decode_message, encode_message


def encode_stream_message(msg_type: MessageType, payload: dict[str, Any]) -> bytes:
    return encode_message(msg_type, payload).encode("utf-8")


def decode_stream_message(raw: bytes) -> tuple[MessageType, dict[str, Any]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MessageDecodeError("invalid utf-8 stream message") from exc
    return decode_message(text)
