"""libp2p + GossipSub ベースの NetworkTransport 実装。"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from useful_blockchain.network.libp2p.runner import Libp2pPeer, Libp2pRunner
from useful_blockchain.network.messages import MessageType
from useful_blockchain.network.peer import PeerConnection
from useful_blockchain.types import NetworkSettings

logger = logging.getLogger(__name__)

IncomingHandler = Callable[[str, MessageType, dict[str, Any]], Awaitable[None]]
DisconnectHandler = Callable[[str], Awaitable[None]]


def _is_multiaddr(url: str) -> bool:
    return url.startswith("/ip")


class Libp2pTransport:
    def __init__(
        self,
        settings: NetworkSettings,
        node_id: str,
        on_message: IncomingHandler,
        on_disconnect: DisconnectHandler | None = None,
    ) -> None:
        self._settings = settings
        self._node_id = node_id
        self._on_message = on_message
        self._on_disconnect = on_disconnect
        self._runner = Libp2pRunner(
            settings.libp2p,
            node_id,
            on_message,
            on_disconnect,
        )

    @property
    def local_url(self) -> str:
        if self._runner.local_multiaddr:
            return self._runner.local_multiaddr
        port = self._settings.libp2p.listen_port or self._settings.port
        return f"/ip4/127.0.0.1/tcp/{port}"

    @property
    def actual_port(self) -> int:
        return self._runner.listen_port or self._settings.libp2p.listen_port or self._settings.port

    @property
    def _actual_port(self) -> int:
        return self.actual_port

    @property
    def peers(self) -> dict[str, PeerConnection]:
        # Libp2pPeer は PeerConnection と同じ属性を持つ
        return self._runner.peers  # type: ignore[return-value]

    async def start(self) -> None:
        import asyncio

        loop = asyncio.get_running_loop()
        await self._runner.start(loop)
        import asyncio

        await asyncio.sleep(0.5)
        for addr in self._settings.libp2p.bootstrap_peers:
            await self.connect_peer(addr)
            await asyncio.sleep(0.3)

    async def stop(self) -> None:
        await self._runner.stop()

    async def connect_peer(self, url: str) -> str | None:
        if not url or url == self.local_url:
            return None
        if not _is_multiaddr(url):
            logger.warning("libp2p transport expects multiaddr, got: %s", url)
            return None
        try:
            import multiaddr
            from libp2p.peer.peerinfo import info_from_p2p_addr

            info = info_from_p2p_addr(multiaddr.Multiaddr(url))
            peer_id = info.peer_id.to_string()
        except Exception:
            logger.warning("invalid libp2p multiaddr: %s", url, exc_info=True)
            return None
        self._runner.connect(url)
        if peer_id not in self._runner.peers:
            self._runner.peers[peer_id] = Libp2pPeer(peer_id)
        return peer_id

    async def broadcast(self, msg_type: MessageType, payload: dict[str, Any]) -> None:
        if msg_type == MessageType.NEW_BLOCK:
            self._runner.publish_block(payload)
            return
        self._runner.broadcast_stream(msg_type, payload)

    async def send_to_peer(
        self, peer_id: str, msg_type: MessageType, payload: dict[str, Any]
    ) -> None:
        if msg_type == MessageType.NEW_BLOCK:
            self._runner.publish_block(payload)
            return
        self._runner.send_stream(peer_id, msg_type, payload)
