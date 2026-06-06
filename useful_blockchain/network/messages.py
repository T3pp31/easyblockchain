"""P2P メッセージ定義とシリアライズ。"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    HELLO = "HELLO"
    PEERS = "PEERS"
    GET_CHAIN = "GET_CHAIN"
    CHAIN_RESPONSE = "CHAIN_RESPONSE"
    NEW_BLOCK = "NEW_BLOCK"
    PING = "PING"
    PONG = "PONG"


def encode_message(msg_type: MessageType, payload: dict[str, Any]) -> str:
    body = {"type": msg_type.value, **payload}
    return json.dumps(body, sort_keys=True)


def decode_message(raw: str) -> tuple[MessageType, dict[str, Any]]:
    data = json.loads(raw)
    if not isinstance(data, dict) or "type" not in data:
        raise ValueError("Invalid message format")
    msg_type = MessageType(data["type"])
    payload = {k: v for k, v in data.items() if k != "type"}
    return msg_type, payload
