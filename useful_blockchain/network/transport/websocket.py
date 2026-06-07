"""WebSocket ベースの NetworkTransport 実装。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from useful_blockchain.network.messages import MessageType
from useful_blockchain.network.peer import PeerConnection
from useful_blockchain.network.server import P2PServer
from useful_blockchain.types import NetworkSettings

IncomingHandler = Callable[[str, MessageType, dict[str, Any]], Awaitable[None]]
DisconnectHandler = Callable[[str], Awaitable[None]]


class WebSocketTransport:
    def __init__(
        self,
        settings: NetworkSettings,
        node_id: str,
        on_message: IncomingHandler,
        on_disconnect: DisconnectHandler | None = None,
    ) -> None:
        self._server = P2PServer(settings, node_id, on_message, on_disconnect)

    @property
    def local_url(self) -> str:
        return self._server.local_url

    @property
    def actual_port(self) -> int:
        return self._server.actual_port

    @property
    def _actual_port(self) -> int:
        return self._server.actual_port

    @property
    def peers(self) -> dict[str, PeerConnection]:
        return self._server.peers

    async def start(self) -> None:
        await self._server.start()

    async def stop(self) -> None:
        await self._server.stop()

    async def connect_peer(self, url: str) -> str | None:
        return await self._server.connect_peer(url)

    async def broadcast(self, msg_type: MessageType, payload: dict[str, Any]) -> None:
        await self._server.broadcast(msg_type, payload)

    async def send_to_peer(
        self, peer_id: str, msg_type: MessageType, payload: dict[str, Any]
    ) -> None:
        await self._server.send_to_peer(peer_id, msg_type, payload)
