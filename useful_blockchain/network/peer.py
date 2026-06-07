"""ピア接続管理。"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from typing import Any, Awaitable, Callable

import websockets
from websockets.exceptions import PayloadTooBig

from useful_blockchain.network.messages import MessageType, decode_message, encode_message
from useful_blockchain.network.peer_url import PeerConnectTarget
from useful_blockchain.network.rate_limit import SlidingWindowRateLimiter
from useful_blockchain.types import RateLimitSettings

logger = logging.getLogger(__name__)

MessageHandler = Callable[[str, MessageType, dict[str, Any]], Awaitable[None]]


class PeerConnection:
    def __init__(
        self,
        peer_id: str,
        websocket: Any,
        on_message: MessageHandler,
        max_message_bytes: int = 1_048_576,
        require_auth: bool = True,
        rate_limit_settings: RateLimitSettings | None = None,
        on_closed: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.peer_id = peer_id
        self.websocket = websocket
        self.on_message = on_message
        self._max_message_bytes = max_message_bytes
        self._require_auth = require_auth
        self._closed = False
        self._authenticated = not require_auth
        self._decode_errors = 0
        self._on_closed = on_closed
        self._rate_limit_settings = rate_limit_settings or RateLimitSettings()
        self._message_limiter = SlidingWindowRateLimiter(
            self._rate_limit_settings.max_messages_per_peer_per_second,
            window_seconds=1.0,
        )
        self.last_ping_at: float | None = None
        self.last_pong_at: float | None = None

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    def mark_authenticated(self) -> None:
        self._authenticated = True

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
                if not self._message_limiter.allow(self.peer_id):
                    logger.warning("Message rate limit exceeded for %s", self.peer_id)
                    await self.close()
                    return
                try:
                    msg_type, payload = decode_message(str(raw))
                except (json.JSONDecodeError, ValueError) as exc:
                    self._decode_errors += 1
                    preview = str(raw)[:200]
                    logger.warning(
                        "Decode error from %s: %s (preview=%r)",
                        self.peer_id,
                        exc,
                        preview,
                    )
                    if (
                        self._decode_errors
                        >= self._rate_limit_settings.max_decode_errors_before_disconnect
                    ):
                        logger.warning("Too many decode errors from %s; closing", self.peer_id)
                        await self.close()
                        return
                    continue

                if self._require_auth and not self._authenticated and msg_type != MessageType.HELLO:
                    logger.warning(
                        "Unauthenticated message %s from %s; closing",
                        msg_type.value,
                        self.peer_id,
                    )
                    await self.close()
                    return

                await self.on_message(self.peer_id, msg_type, payload)
        except PayloadTooBig:
            logger.warning("Payload too large from %s", self.peer_id)
        except websockets.ConnectionClosed:
            logger.debug("Connection closed: %s", self.peer_id)
        finally:
            self._closed = True
            if self._on_closed is not None:
                await self._on_closed(self.peer_id)

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
    ssl_context: ssl.SSLContext | None = None,
    require_auth: bool = True,
    rate_limit_settings: RateLimitSettings | None = None,
    on_closed: Callable[[str], Awaitable[None]] | None = None,
    connect_target: PeerConnectTarget | None = None,
) -> PeerConnection:
    connect_kwargs: dict[str, Any] = {"max_size": max_size}
    if ssl_context is not None:
        connect_kwargs["ssl"] = ssl_context
    if connect_target is not None:
        connect_kwargs["host"] = connect_target.host
        connect_kwargs["port"] = connect_target.port
    connect_url = connect_target.url if connect_target is not None else url
    websocket = await asyncio.wait_for(
        websockets.connect(connect_url, **connect_kwargs),
        timeout=timeout,
    )
    peer = PeerConnection(
        peer_id,
        websocket,
        on_message,
        max_message_bytes=max_message_bytes,
        require_auth=require_auth,
        rate_limit_settings=rate_limit_settings,
        on_closed=on_closed,
    )
    asyncio.create_task(peer.listen())
    return peer
