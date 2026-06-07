"""P2P WebSocket サーバー。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable

from websockets.asyncio.server import Server, ServerConnection, serve

from useful_blockchain.network.messages import MessageType
from useful_blockchain.network.peer import PeerConnection
from useful_blockchain.types import NetworkSettings

logger = logging.getLogger(__name__)

IncomingHandler = Callable[[str, MessageType, dict[str, Any]], Awaitable[None]]


class P2PServer:
    def __init__(
        self,
        settings: NetworkSettings,
        node_id: str,
        on_message: IncomingHandler,
    ) -> None:
        self.settings = settings
        self.node_id = node_id
        self.on_message = on_message
        self.peers: dict[str, PeerConnection] = {}
        self._server: Server | None = None
        self._actual_port = settings.port
        self._local_url = f"ws://{settings.host}:{settings.port}"

    @property
    def local_url(self) -> str:
        host = "127.0.0.1" if self.settings.host in ("0.0.0.0", "") else self.settings.host
        return f"ws://{host}:{self._actual_port}"

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        peer_id = str(uuid.uuid4())
        peer = PeerConnection(peer_id, websocket, self._route_message)
        self.peers[peer_id] = peer
        try:
            await peer.listen()
        finally:
            self.peers.pop(peer_id, None)

    async def _route_message(
        self, peer_id: str, msg_type: MessageType, payload: dict[str, Any]
    ) -> None:
        await self.on_message(peer_id, msg_type, payload)

    async def start(self) -> None:
        self._server = await serve(
            self._handle_connection,
            self.settings.host,
            self.settings.port,
        )
        if self._server.sockets:
            self._actual_port = self._server.sockets[0].getsockname()[1]
        logger.info("P2P server listening on %s:%s", self.settings.host, self._actual_port)

    async def stop(self) -> None:
        for peer in list(self.peers.values()):
            try:
                await asyncio.wait_for(peer.close(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
        self.peers.clear()
        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=3.0)
            except asyncio.TimeoutError:
                pass
            self._server = None

    async def connect_peer(self, url: str) -> str | None:
        if len(self.peers) >= self.settings.max_peers:
            return None
        try:
            from useful_blockchain.network.peer import connect_to_peer

            peer_id = str(uuid.uuid4())
            peer = await connect_to_peer(
                url,
                peer_id,
                self._route_message,
                timeout=self.settings.connection_timeout_seconds,
            )
            self.peers[peer_id] = peer
            return peer_id
        except Exception as exc:
            logger.warning("Failed to connect to %s: %s", url, exc)
            return None

    async def broadcast(self, msg_type: MessageType, payload: dict[str, Any]) -> None:
        for peer in list(self.peers.values()):
            if not peer.closed:
                try:
                    await peer.send(msg_type, payload)
                except Exception as exc:
                    logger.warning("Broadcast failed to %s: %s", peer.peer_id, exc)

    async def send_to_peer(
        self, peer_id: str, msg_type: MessageType, payload: dict[str, Any]
    ) -> None:
        peer = self.peers.get(peer_id)
        if peer and not peer.closed:
            await peer.send(msg_type, payload)
