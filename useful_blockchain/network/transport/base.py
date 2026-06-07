"""NetworkTransport 抽象インターフェース。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from useful_blockchain.network.messages import MessageType
from useful_blockchain.network.peer import PeerConnection
from useful_blockchain.types import NetworkSettings

IncomingHandler = Callable[[str, MessageType, dict[str, Any]], Awaitable[None]]
DisconnectHandler = Callable[[str], Awaitable[None]]


class NetworkTransport(Protocol):
    @property
    def local_url(self) -> str: ...

    @property
    def actual_port(self) -> int: ...

    @property
    def peers(self) -> dict[str, PeerConnection]: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def connect_peer(self, url: str) -> str | None: ...

    async def broadcast(self, msg_type: MessageType, payload: dict[str, Any]) -> None: ...

    async def send_to_peer(
        self, peer_id: str, msg_type: MessageType, payload: dict[str, Any]
    ) -> None: ...


def create_transport(
    settings: NetworkSettings,
    node_id: str,
    on_message: IncomingHandler,
    on_disconnect: DisconnectHandler | None = None,
) -> NetworkTransport:
    if settings.transport == "libp2p":
        from useful_blockchain.network.transport.libp2p_transport import Libp2pTransport

        return Libp2pTransport(settings, node_id, on_message, on_disconnect)
    from useful_blockchain.network.transport.websocket import WebSocketTransport

    return WebSocketTransport(settings, node_id, on_message, on_disconnect)
