"""trio 上で libp2p Host + GossipSub を動かし asyncio と橋渡しする。"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable

from useful_blockchain.network.libp2p.protocols import decode_stream_message, encode_stream_message
from useful_blockchain.network.libp2p.topics import (
    BLOCKS_TOPIC,
    CHAIN_SYNC_PROTOCOL,
    GOSSIPSUB_PROTOCOL,
)
from useful_blockchain.network.messages import MessageType
from useful_blockchain.types import Libp2pSettings

logger = logging.getLogger(__name__)

IncomingHandler = Callable[[str, MessageType, dict[str, Any]], Awaitable[None]]


class _CommandType(str, Enum):
    STOP = "stop"
    CONNECT = "connect"
    PUBLISH_BLOCK = "publish_block"
    SEND_STREAM = "send_stream"
    BROADCAST_STREAM = "broadcast_stream"


@dataclass
class _Command:
    type: _CommandType
    payload: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.payload is None:
            self.payload = {}


class Libp2pPeer:
    """Node が期待するピア属性の libp2p 向けアダプタ。"""

    def __init__(self, peer_id: str) -> None:
        self.peer_id = peer_id
        self.closed = False
        self.authenticated = False
        self.last_ping_at: float | None = None
        self.last_pong_at: float | None = None

    def mark_authenticated(self) -> None:
        self.authenticated = True

    async def close(self) -> None:
        self.closed = True


class Libp2pRunner:
    def __init__(
        self,
        settings: Libp2pSettings,
        node_id: str,
        on_message: IncomingHandler,
        on_disconnect: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._settings = settings
        self._node_id = node_id
        self._on_message = on_message
        self._on_disconnect = on_disconnect
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._cmd_queue: queue.Queue[_Command] = queue.Queue()
        self.peers: dict[str, Libp2pPeer] = {}
        self._peer_id_str = ""
        self._listen_port = 0
        self._local_multiaddr = ""

    @property
    def peer_id(self) -> str:
        return self._peer_id_str

    @property
    def listen_port(self) -> int:
        return self._listen_port

    @property
    def local_multiaddr(self) -> str:
        return self._local_multiaddr

    async def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._thread = threading.Thread(target=self._run_trio, name="libp2p-runner", daemon=True)
        self._thread.start()
        ready = await asyncio.to_thread(self._ready.wait, 30)
        if not ready:
            raise RuntimeError("libp2p runner failed to start within timeout")

    async def stop(self) -> None:
        self._cmd_queue.put(_Command(_CommandType.STOP))
        if self._thread is not None:
            await asyncio.to_thread(self._thread.join, 10)
        self._stopped.set()

    def connect(self, multiaddr: str) -> None:
        self._cmd_queue.put(_Command(_CommandType.CONNECT, {"multiaddr": multiaddr}))

    def publish_block(self, payload: dict[str, Any]) -> None:
        self._cmd_queue.put(_Command(_CommandType.PUBLISH_BLOCK, {"payload": payload}))

    def send_stream(
        self, peer_id: str, msg_type: MessageType, payload: dict[str, Any]
    ) -> None:
        self._cmd_queue.put(
            _Command(
                _CommandType.SEND_STREAM,
                {"peer_id": peer_id, "msg_type": msg_type, "payload": payload},
            )
        )

    def broadcast_stream(self, msg_type: MessageType, payload: dict[str, Any]) -> None:
        self._cmd_queue.put(
            _Command(
                _CommandType.BROADCAST_STREAM,
                {"msg_type": msg_type, "payload": payload},
            )
        )

    def _run_trio(self) -> None:
        import trio

        try:
            trio.run(self._trio_main)
        except Exception:
            logger.exception("libp2p trio loop crashed")
        finally:
            self._stopped.set()

    def _dispatch_to_asyncio(
        self, peer_id: str, msg_type: MessageType, payload: dict[str, Any]
    ) -> None:
        if self._loop is None:
            return

        async def _invoke() -> None:
            await self._on_message(peer_id, msg_type, payload)

        asyncio.run_coroutine_threadsafe(_invoke(), self._loop)

    def _dispatch_disconnect(self, peer_id: str) -> None:
        if self._loop is None or self._on_disconnect is None:
            return
        asyncio.run_coroutine_threadsafe(self._on_disconnect(peer_id), self._loop)

    async def _trio_main(self) -> None:
        import multiaddr
        import trio
        from libp2p import new_host
        from libp2p.crypto.ed25519 import create_new_key_pair
        from libp2p.custom_types import TProtocol
        from libp2p.peer.id import ID
        from libp2p.peer.peerinfo import info_from_p2p_addr
        from libp2p.pubsub.gossipsub import GossipSub
        from libp2p.pubsub.pubsub import Pubsub
        from libp2p.stream_muxer.mplex.mplex import MPLEX_PROTOCOL_ID, Mplex
        from libp2p.tools.async_service.trio_service import background_trio_service
        from libp2p.utils.address_validation import find_free_port

        port = self._settings.listen_port or find_free_port()
        listen = multiaddr.Multiaddr(f"/ip4/0.0.0.0/tcp/{port}")
        host = new_host(
            key_pair=create_new_key_pair(),
            muxer_opt={MPLEX_PROTOCOL_ID: Mplex},
            listen_addrs=[listen],
            enable_mDNS=False,
        )

        async def _stream_handler(stream: Any) -> None:
            try:
                raw = await stream.read()
                if not raw:
                    return
                msg_type, payload = decode_stream_message(raw)
                peer_id = str(stream.muxed_conn.peer_id)
                self._dispatch_to_asyncio(peer_id, msg_type, payload)
            except Exception:
                logger.exception("libp2p stream handler error")
            finally:
                await stream.close()

        host.set_stream_handler(TProtocol(CHAIN_SYNC_PROTOCOL), _stream_handler)

        gossipsub = GossipSub(
            protocols=[TProtocol(GOSSIPSUB_PROTOCOL)],
            degree=self._settings.gossipsub_mesh_n,
            degree_low=max(2, self._settings.gossipsub_mesh_n - 2),
            degree_high=self._settings.gossipsub_mesh_n + 2,
            heartbeat_interval=self._settings.gossipsub_heartbeat_interval,
        )
        pubsub = Pubsub(host, gossipsub)

        stop_event = trio.Event()
        async with host.run(listen_addrs=[listen]), trio.open_nursery() as nursery:
            nursery.start_soon(host.get_peerstore().start_cleanup_task, 60)
            async with background_trio_service(pubsub):
                async with background_trio_service(gossipsub):
                    await pubsub.wait_until_ready()
                    subscription = await pubsub.subscribe(BLOCKS_TOPIC)

                    self._peer_id_str = host.get_id().to_string()
                    addrs = host.get_addrs()
                    if addrs:
                        self._local_multiaddr = f"{addrs[0]}/p2p/{self._peer_id_str}"
                        try:
                            self._listen_port = int(addrs[0].value_for_protocol("tcp"))
                        except Exception:
                            self._listen_port = port
                    else:
                        self._local_multiaddr = (
                            f"/ip4/127.0.0.1/tcp/{port}/p2p/{self._peer_id_str}"
                        )
                        self._listen_port = port

                    self._ready.set()
                    nursery.start_soon(self._receive_blocks, subscription, stop_event)
                    nursery.start_soon(self._command_loop, host, pubsub, stop_event)
                    await stop_event.wait()
                    nursery.cancel_scope.cancel()

        self._stopped.set()

    async def _receive_blocks(self, subscription: Any, stop_event: Any) -> None:
        import trio

        while not stop_event.is_set():
            try:
                with trio.move_on_after(1.0) as cancel_scope:
                    message = await subscription.get()
                if cancel_scope.cancelled_caught or message is None:
                    continue
                from libp2p.peer.id import ID

                peer_id = ID(message.from_id).to_string()
                data = json.loads(message.data.decode("utf-8"))
                msg_type = MessageType(data["type"])
                payload = {k: v for k, v in data.items() if k != "type"}
                if msg_type == MessageType.NEW_BLOCK:
                    self._dispatch_to_asyncio(peer_id, msg_type, payload)
            except Exception:
                await trio.sleep(0.1)

    async def _command_loop(self, host: Any, pubsub: Any, stop_event: Any) -> None:
        import multiaddr
        import trio
        from libp2p.peer.peerinfo import info_from_p2p_addr

        while not stop_event.is_set():
            try:
                cmd = await trio.to_thread.run_sync(self._cmd_queue.get, True, 0.2)
            except queue.Empty:
                continue
            if cmd.type == _CommandType.STOP:
                stop_event.set()
                break
            if cmd.type == _CommandType.CONNECT:
                maddr_str = str(cmd.payload.get("multiaddr", ""))
                if not maddr_str:
                    continue
                try:
                    maddr = multiaddr.Multiaddr(maddr_str)
                    info = info_from_p2p_addr(maddr)
                    await host.connect(info)
                    peer_id = info.peer_id.to_string()
                    if peer_id not in self.peers:
                        self.peers[peer_id] = Libp2pPeer(peer_id)
                except Exception:
                    logger.warning("libp2p connect failed: %s", maddr_str, exc_info=True)
            elif cmd.type == _CommandType.PUBLISH_BLOCK:
                payload = cmd.payload.get("payload", {})
                body = json.dumps({"type": MessageType.NEW_BLOCK.value, **payload}, sort_keys=True)
                await pubsub.publish(BLOCKS_TOPIC, body.encode("utf-8"))
            elif cmd.type == _CommandType.SEND_STREAM:
                await self._send_on_stream(host, cmd.payload)
            elif cmd.type == _CommandType.BROADCAST_STREAM:
                await self._broadcast_on_streams(host, cmd.payload)

    async def _send_on_stream(self, host: Any, payload: dict[str, Any]) -> None:
        from libp2p.custom_types import TProtocol
        from libp2p.peer.id import ID

        peer_id = str(payload.get("peer_id", ""))
        msg_type = payload.get("msg_type")
        msg_payload = payload.get("payload", {})
        if not peer_id or not isinstance(msg_type, MessageType):
            return
        try:
            stream = await host.new_stream(ID.from_string(peer_id), [TProtocol(CHAIN_SYNC_PROTOCOL)])
            await stream.write(encode_stream_message(msg_type, msg_payload))
            await stream.close()
        except Exception:
            logger.warning("libp2p stream send failed to %s", peer_id, exc_info=True)

    async def _broadcast_on_streams(self, host: Any, payload: dict[str, Any]) -> None:
        msg_type = payload.get("msg_type")
        msg_payload = payload.get("payload", {})
        if not isinstance(msg_type, MessageType):
            return
        for peer_id in list(self.peers.keys()):
            await self._send_on_stream(
                host,
                {"peer_id": peer_id, "msg_type": msg_type, "payload": msg_payload},
            )
