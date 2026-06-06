"""ピア接続管理。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

import websockets

from useful_blockchain.network.messages import MessageType, decode_message, encode_message

logger = logging.getLogger(__name__)

MessageHandler = Callable[[str, MessageType, dict[str, Any]], Awaitable[None]]


class PeerConnection:
    def __init__(
        self,
        peer_id: str,
        websocket: Any,
        on_message: MessageHandler,
    ) -> None:
        self.peer_id = peer_id
        self.websocket = websocket
        self.on_message = on_message
        self._closed = False

    async def send(self, msg_type: MessageType, payload: dict[str, Any]) -> None:
        if self._closed:
            return
        await self.websocket.send(encode_message(msg_type, payload))

    async def listen(self) -> None:
        try:
            async for raw in self.websocket:
                msg_type, payload = decode_message(str(raw))
                await self.on_message(self.peer_id, msg_type, payload)
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
) -> PeerConnection:
    websocket = await asyncio.wait_for(websockets.connect(url), timeout=timeout)
    peer = PeerConnection(peer_id, websocket, on_message)
    asyncio.create_task(peer.listen())
    return peer
