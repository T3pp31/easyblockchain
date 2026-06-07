"""ピア接続管理。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

import websockets
from websockets.exceptions import PayloadTooBig

from useful_blockchain.network.messages import MessageType, decode_message, encode_message

logger = logging.getLogger(__name__)

MessageHandler = Callable[[str, MessageType, dict[str, Any]], Awaitable[None]]


class PeerConnection:
    def __init__(
        self,
        peer_id: str,
        websocket: Any,
        on_message: MessageHandler,
        max_message_bytes: int = 1_048_576,
    ) -> None:
        self.peer_id = peer_id
        self.websocket = websocket
        self.on_message = on_message
        self._max_message_bytes = max_message_bytes
        self._closed = False

    async def send(self, msg_type: MessageType, payload: dict[str, Any]) -> None:
        if self._closed:
            return
        encoded = encode_message(msg_type, payload)
        if len(encoded.encode("utf-8")) > self._max_message_bytes:
            logger.warning(
                "Message too large to send to %s: %d bytes (max %d)",
                self.peer_id,
                len(encoded.encode("utf-8")),
                self._max_message_bytes,
            )
            return
        await self.websocket.send(encoded)

    async def listen(self) -> None:
        try:
            async for raw in self.websocket:
                try:
                    msg_type, payload = decode_message(str(raw))
                except (json.JSONDecodeError, ValueError) as exc:
                    preview = str(raw)[:200]
                    logger.warning(
                        "Decode error from %s: %s (preview=%r)",
                        self.peer_id,
                        exc,
                        preview,
                    )
                    continue
                await self.on_message(self.peer_id, msg_type, payload)
        except PayloadTooBig:
            logger.warning("Payload too large from %s", self.peer_id)
        except websockets.ConnectionClosed:
            logger.debug("Connection closed: %s", self.peer_id)
        finally:
            self._closed = True

    async def close(self) -> None:
        self._closed = True
        await self.websocket.close()

    @property
    def closed(self) -> bool:
        return self._closed


async def connect_to_peer(
    url: str,
    peer_id: str,
    on_message: MessageHandler,
    timeout: float = 10.0,
    max_size: int = 1_048_576,
    max_message_bytes: int = 1_048_576,
) -> PeerConnection:
    websocket = await asyncio.wait_for(
        websockets.connect(url, max_size=max_size),
        timeout=timeout,
    )
    peer = PeerConnection(peer_id, websocket, on_message, max_message_bytes=max_message_bytes)
    asyncio.create_task(peer.listen())
    return peer
