"""P2P WebSocket サーバー。"""

from __future__ import annotations

import asyncio
import logging
import ssl
import uuid
from typing import Any, Awaitable, Callable

from websockets.asyncio.server import Server, ServerConnection, serve

from useful_blockchain.network.messages import MessageType
from useful_blockchain.network.peer import PeerConnection
from useful_blockchain.network.peer_url import resolve_peer_connect_target
from useful_blockchain.network.rate_limit import SlidingWindowRateLimiter
from useful_blockchain.network.tls import (
    build_server_ssl_context,
    rejects_plain_websocket,
    websocket_scheme,
)
from useful_blockchain.types import Environment, NetworkSettings

logger = logging.getLogger(__name__)

IncomingHandler = Callable[[str, MessageType, dict[str, Any]], Awaitable[None]]
DisconnectHandler = Callable[[str], Awaitable[None]]


class P2PServer:
    def __init__(
        self,
        settings: NetworkSettings,
        node_id: str,
        on_message: IncomingHandler,
        on_disconnect: DisconnectHandler | None = None,
        environment: Environment = "development",
    ) -> None:
        self.settings = settings
        self._environment = environment
        self.node_id = node_id
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        self.peers: dict[str, PeerConnection] = {}
        self.peer_urls: dict[str, str] = {}
        self._peer_lock = asyncio.Lock()
        self._server: Server | None = None
        self._actual_port = settings.port
        self._connection_limiter = SlidingWindowRateLimiter(
            settings.rate_limit.max_connections_per_ip_per_minute,
            window_seconds=60.0,
        )
        self._ssl_context: ssl.SSLContext | None = None
        if settings.tls.enabled:
            self._ssl_context = build_server_ssl_context(settings.tls)

    @property
    def local_url(self) -> str:
        host = "127.0.0.1" if self.settings.host in ("0.0.0.0", "") else self.settings.host
        scheme = websocket_scheme(self.settings.tls.enabled)
        return f"{scheme}://{host}:{self._actual_port}"

    def _client_ip(self, websocket: ServerConnection) -> str:
        remote = websocket.remote_address
        if remote is None:
            return "unknown"
        return str(remote[0])

    async def _handle_peer_closed(self, peer_id: str) -> None:
        async with self._peer_lock:
            self.peers.pop(peer_id, None)
            self.peer_urls.pop(peer_id, None)
        if self.on_disconnect is not None:
            await self.on_disconnect(peer_id)

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        client_ip = self._client_ip(websocket)
        if not self._connection_limiter.allow(client_ip):
            await websocket.close(1013, "rate limit exceeded")
            logger.warning("Rejected inbound connection from %s: rate limit", client_ip)
            return

        async with self._peer_lock:
            if len(self.peers) >= self.settings.max_peers:
                await websocket.close(1013, "max peers reached")
                logger.warning("Rejected inbound connection: max_peers reached")
                return
            peer_id = str(uuid.uuid4())
            peer = PeerConnection(
                peer_id,
                websocket,
                self._route_message,
                max_message_bytes=self.settings.max_message_bytes,
                require_auth=self.settings.peer_auth.enabled,
                rate_limit_settings=self.settings.rate_limit,
                on_closed=self._handle_peer_closed,
            )
            self.peers[peer_id] = peer
        try:
            await peer.listen()
        finally:
            async with self._peer_lock:
                self.peers.pop(peer_id, None)
                self.peer_urls.pop(peer_id, None)

    async def _route_message(
        self, peer_id: str, msg_type: MessageType, payload: dict[str, Any]
    ) -> None:
        await self.on_message(peer_id, msg_type, payload)

    async def start(self) -> None:
        serve_kwargs: dict[str, Any] = {
            "max_size": self.settings.max_message_bytes,
        }
        if self._ssl_context is not None:
            serve_kwargs["ssl"] = self._ssl_context
        self._server = await serve(
            self._handle_connection,
            self.settings.host,
            self.settings.port,
            **serve_kwargs,
        )
        if self._server.sockets:
            self._actual_port = self._server.sockets[0].getsockname()[1]
        logger.info("P2P server listening on %s:%s", self.settings.host, self._actual_port)
        if (
            self._environment == "production"
            and self.settings.host in ("0.0.0.0", "")
        ):
            logger.info(
                "Production node bound to all interfaces; restrict P2P port %s with "
                "firewall or Kubernetes NetworkPolicy",
                self._actual_port,
            )

    async def stop(self) -> None:
        for peer in list(self.peers.values()):
            try:
                await asyncio.wait_for(
                    peer.close(), timeout=self.settings.shutdown_peer_close_timeout_seconds
                )
            except asyncio.TimeoutError:
                pass
        self.peers.clear()
        self.peer_urls.clear()
        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(
                    self._server.wait_closed(),
                    timeout=self.settings.shutdown_server_wait_timeout_seconds,
                )
            except asyncio.TimeoutError:
                pass
            self._server = None

    async def connect_peer(self, url: str) -> str | None:
        from useful_blockchain.network.tls import build_client_ssl_context

        if not url.startswith("ws://") and not url.startswith("wss://"):
            logger.warning("Invalid peer URL scheme: %s", url)
            return None

        if url.startswith("ws://") and rejects_plain_websocket(
            self.settings.tls.enabled, self._environment
        ):
            logger.warning(
                "Rejected plain WebSocket outbound connection in production/TLS mode: %s",
                url,
            )
            return None

        async with self._peer_lock:
            if len(self.peers) >= self.settings.max_peers:
                return None
        connect_target = resolve_peer_connect_target(
            url, self.settings, self._environment
        )
        if connect_target is None:
            return None

        try:
            from useful_blockchain.network.peer import connect_to_peer

            ssl_context: ssl.SSLContext | None = None
            if url.startswith("wss://"):
                ssl_context = build_client_ssl_context(self.settings.tls)

            peer_id = str(uuid.uuid4())
            peer = await connect_to_peer(
                url,
                peer_id,
                self._route_message,
                timeout=self.settings.connection_timeout_seconds,
                max_size=self.settings.max_message_bytes,
                max_message_bytes=self.settings.max_message_bytes,
                ssl_context=ssl_context,
                require_auth=self.settings.peer_auth.enabled,
                rate_limit_settings=self.settings.rate_limit,
                on_closed=self._handle_peer_closed,
                connect_target=connect_target,
            )
            async with self._peer_lock:
                if len(self.peers) >= self.settings.max_peers:
                    await peer.close()
                    return None
                self.peers[peer_id] = peer
                self.peer_urls[peer_id] = url
            return peer_id
        except Exception as exc:
            logger.warning("Failed to connect to %s: %s", url, exc)
            return None

    def get_peer_url(self, peer_id: str) -> str | None:
        return self.peer_urls.get(peer_id)

    def active_peer_count(self) -> int:
        return sum(1 for peer in self.peers.values() if not peer.closed)

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
