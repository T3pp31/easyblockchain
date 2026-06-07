"""ノードオーケストレータ。"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from useful_blockchain.blockchain import BlockChain
from useful_blockchain.consensus.factory import create_consensus
from useful_blockchain.hash_utils import genesis_hash
from useful_blockchain.network.discovery import PeerDiscovery
from useful_blockchain.network.peer_url import validate_peer_url
from useful_blockchain.network.messages import MessageType
from useful_blockchain.network.peer_auth import build_hello_payload, verify_hello
from useful_blockchain.network.reconnect import ReconnectManager
from useful_blockchain.network.server import P2PServer
from useful_blockchain.observability.health_server import HealthServer
from useful_blockchain.observability.metrics import MetricsCollector
from useful_blockchain.persistence import ChainStore, ChainStoreError, PersistedState
from useful_blockchain.settings import load_settings_with_overrides
from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import Block

logger = logging.getLogger(__name__)

_VALIDATOR_PRIVATE_KEY_ENV = "EASYBLOCKCHAIN_VALIDATOR_PRIVATE_KEY"
_P2P_IDENTITY_KEY_ENV = "EASYBLOCKCHAIN_P2P_IDENTITY_KEY"


def _load_private_key_pem_from_env(env_name: str) -> bytes | None:
    value = os.environ.get(env_name)
    if not value:
        return None
    return value.encode("utf-8")


def _resolve_get_chain_batch_size(limit_raw: Any, max_batch: int) -> int:
    if limit_raw is not None:
        try:
            requested = int(limit_raw)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid GET_CHAIN limit %r; using max batch size %s",
                limit_raw,
                max_batch,
            )
            requested = max_batch
    else:
        requested = max_batch
    batch_size = max(1, min(requested, max_batch))
    if batch_size != requested:
        logger.warning(
            "Clamped GET_CHAIN limit from %s to %s (max=%s)",
            requested,
            batch_size,
            max_batch,
        )
    return batch_size


def _resolve_get_chain_from_height(from_height_raw: Any) -> int:
    if from_height_raw is None:
        return 1
    try:
        requested = int(from_height_raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid GET_CHAIN from_height %r; using 1",
            from_height_raw,
        )
        return 1
    if requested < 1:
        logger.warning(
            "Clamped GET_CHAIN from_height from %s to 1",
            requested,
        )
        return 1
    return requested


@dataclass
class _ChainSyncSession:
    blocks: list[Block] = field(default_factory=list)
    done: asyncio.Event = field(default_factory=asyncio.Event)


class Node:
    def __init__(
        self,
        config_path: str | Path | None = None,
        overrides: dict[str, Any] | None = None,
        genesis_stakes: dict[str, int] | None = None,
        validator_private_key_pem: bytes | None = None,
        p2p_identity_key_pem: bytes | None = None,
    ) -> None:
        self.settings = load_settings_with_overrides(config_path, overrides)
        self._data_dir = Path(self.settings.node.data_dir).expanduser().resolve(
            strict=False
        )
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._store = ChainStore(self.settings.persistence)

        persisted = self._load_persisted_state()
        if persisted is not None and persisted.node_id:
            self.node_id = persisted.node_id
        else:
            self.node_id = self.settings.node.node_id or str(uuid.uuid4())

        if persisted is not None and persisted.genesis_stakes:
            self.genesis_stakes = dict(persisted.genesis_stakes)
        else:
            self.genesis_stakes = dict(genesis_stakes or {})

        validator_pem = validator_private_key_pem
        if validator_pem is None:
            validator_pem = _load_private_key_pem_from_env(_VALIDATOR_PRIVATE_KEY_ENV)
        self._validator_key_external = validator_pem is not None

        self.signature_manager = SignatureManager()
        if self.settings.consensus.type == "pos":
            if validator_pem is not None:
                self.signature_manager.import_private_key(validator_pem)
            elif persisted is not None and persisted.private_key_pem is not None:
                self.signature_manager.import_private_key(persisted.private_key_pem)
            else:
                self.signature_manager.generate_key_pair()
            self.enable_signature = True
        else:
            self.enable_signature = False

        p2p_identity_pem = p2p_identity_key_pem
        if p2p_identity_pem is None:
            p2p_identity_pem = _load_private_key_pem_from_env(_P2P_IDENTITY_KEY_ENV)
        self._p2p_identity_key_external = p2p_identity_pem is not None

        self.p2p_identity_manager = SignatureManager()
        if p2p_identity_pem is not None:
            self.p2p_identity_manager.import_private_key(p2p_identity_pem)
        elif persisted is not None and persisted.p2p_identity_pem is not None:
            self.p2p_identity_manager.import_private_key(persisted.p2p_identity_pem)
        else:
            self.p2p_identity_manager.generate_key_pair()

        self.consensus = create_consensus(
            self.settings,
            node_validator_id=self.node_id if self.settings.consensus.type == "pos" else None,
            signature_manager=self.signature_manager,
            genesis_stakes=self.genesis_stakes,
        )
        self.blockchain = BlockChain(
            enable_signature=self.enable_signature or self.settings.consensus.type == "pos",
            consensus=self.consensus,
            genesis_prev_hash=self.settings.genesis.prev_hash,
        )
        if self.settings.consensus.type == "pos":
            from useful_blockchain.consensus.pos import ProofOfStake

            if isinstance(self.consensus, ProofOfStake):
                self.consensus.node_validator_id = self.node_id

        if persisted is not None:
            self._restore_chain(persisted)
        else:
            self._persist_state()

        self._pending_sync: dict[str, _ChainSyncSession] = {}
        self._active_urls: set[str] = set()
        self._url_by_peer: dict[str, str] = {}
        self._reconnect = ReconnectManager(self.settings.network.reconnect)
        self.p2p = P2PServer(
            self.settings.network,
            self.node_id,
            self._handle_message,
            on_disconnect=self._on_peer_disconnected,
            environment=self.settings.node.environment,
        )
        self.discovery = PeerDiscovery(
            self.settings.network,
            self.p2p.local_url,
            self.settings.node.environment,
        )
        self._running = False
        self._ready = False
        self._ping_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._metrics = MetricsCollector(self.settings.observability)
        self._health_server = HealthServer(
            self.settings.observability,
            self._check_readiness,
            self._metrics,
            shutdown_timeout_seconds=self.settings.network.shutdown_server_wait_timeout_seconds,
        )

    def _load_persisted_state(self) -> PersistedState | None:
        try:
            return self._store.load(self._data_dir)
        except ChainStoreError:
            logger.exception("Failed to load persisted state from %s", self._data_dir)
            raise

    def _restore_chain(self, persisted: PersistedState) -> None:
        if persisted.genesis_prev_hash and (
            persisted.genesis_prev_hash != self.settings.genesis.prev_hash
        ):
            raise ValueError(
                "Persisted genesis.prev_hash does not match configuration"
            )
        if not persisted.chain:
            return
        if not self.blockchain.replace_chain(
            persisted.chain, genesis_stakes=self.genesis_stakes
        ):
            raise ValueError("Persisted chain failed integrity verification")
        verification = self.blockchain.verify_chain(
            genesis_stakes=self.genesis_stakes
        )
        if not verification.valid:
            raise ValueError(
                f"Persisted chain is invalid: {verification.reason} "
                f"(index {verification.failed_at_index})"
            )

    def _persist_state(self) -> None:
        private_key_pem: bytes | None = None
        if (
            self.settings.consensus.type == "pos"
            and self.signature_manager.private_key
            and not self._validator_key_external
        ):
            private_key_pem = self.signature_manager.export_private_key()

        p2p_identity_pem: bytes | None = None
        if self.p2p_identity_manager.private_key and not self._p2p_identity_key_external:
            p2p_identity_pem = self.p2p_identity_manager.export_private_key()

        state = PersistedState(
            chain=list(self.blockchain.chain),
            node_id=self.node_id,
            genesis_prev_hash=self.settings.genesis.prev_hash,
            genesis_stakes=dict(self.genesis_stakes),
            private_key_pem=private_key_pem,
            p2p_identity_pem=p2p_identity_pem,
        )
        try:
            self._store.save(self._data_dir, state)
        except ChainStoreError:
            logger.exception("Failed to persist state to %s", self._data_dir)
            raise

    def _hello_payload(self) -> dict[str, Any]:
        return build_hello_payload(
            self.node_id,
            self.settings.consensus.type,
            self.chain_height,
            genesis_hash(self.blockchain.chain, self.settings.genesis.prev_hash),
            self.p2p_identity_manager,
        )

    @property
    def chain_height(self) -> int:
        return len(self.blockchain.chain)

    @property
    def is_ready(self) -> bool:
        return self._ready

    async def _check_readiness(self) -> bool:
        if not self._ready:
            return False
        return self.p2p.active_peer_count() >= self.settings.observability.min_peers_for_ready

    def _update_metrics(self) -> None:
        peer_count = self.p2p.active_peer_count()
        self._metrics.set_chain_height(self.chain_height)
        self._metrics.set_peer_count(peer_count)

    async def start(self) -> None:
        await self.p2p.start()
        await self._health_server.start()
        self.discovery.local_url = self.p2p.local_url

        def _on_peer_found(url: str) -> None:
            asyncio.create_task(self.connect_peer(url))

        self.discovery.start_mdns(on_peer_found=_on_peer_found)
        for peer_url in self.discovery.known_peers:
            await self.connect_peer(peer_url)
        self._running = True
        self._ping_task = asyncio.create_task(self._ping_loop())
        if self.settings.network.reconnect.enabled:
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
        await self._announce_hello()
        self._ready = True
        self._update_metrics()

    async def stop(self) -> None:
        self._running = False
        self._ready = False
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        self.discovery.stop_mdns()
        await self._health_server.stop()
        await self.p2p.stop()
        self._active_urls.clear()
        self._url_by_peer.clear()
        self._persist_state()

    async def _on_peer_disconnected(self, peer_id: str) -> None:
        url = self._url_by_peer.pop(peer_id, None)
        if url:
            self._active_urls.discard(url)
            if self.settings.network.reconnect.enabled:
                self._reconnect.record_failure(url)

    async def connect_peer(self, url: str) -> None:
        if not url or url == self.p2p.local_url or url in self._active_urls:
            return
        if (
            validate_peer_url(url, self.settings.network, self.settings.node.environment)
            is None
        ):
            return
        if not self._reconnect.should_retry(url):
            return
        peer_id = await self.p2p.connect_peer(url)
        if peer_id:
            self._reconnect.record_success(url)
            self._active_urls.add(url)
            self._url_by_peer[peer_id] = url
            await self._send_hello(peer_id)
            if self.settings.network.peer_auth.enabled:
                await self._wait_for_peer_authenticated(peer_id)
            await self.p2p.send_to_peer(
                peer_id,
                MessageType.PEERS,
                {"peers": self.discovery.known_peers + [self.p2p.local_url]},
            )
        else:
            self._reconnect.record_failure(url)

    async def _wait_for_peer_authenticated(
        self, peer_id: str, timeout: float = 5.0
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            peer = self.p2p.peers.get(peer_id)
            if peer is None or peer.closed:
                return
            if peer.authenticated:
                return
            await asyncio.sleep(0.05)

    async def add_block(self, input_data: Any, output_data: Any) -> Block:
        block = self.blockchain.add_new_block(input_data, output_data)
        self._persist_state()
        await self.p2p.broadcast(
            MessageType.NEW_BLOCK,
            {"block": block, "node_id": self.node_id},
        )
        return block

    async def sync_chain(self) -> None:
        self._metrics.inc_sync_operations()
        for peer_id in list(self.p2p.peers.keys()):
            await self._request_chain(peer_id)
        self._update_metrics()

    async def _send_chain_request(self, peer_id: str, from_height: int) -> None:
        await self.p2p.send_to_peer(
            peer_id,
            MessageType.GET_CHAIN,
            {
                "from_height": from_height,
                "limit": self.settings.network.chain_sync_batch_size,
                "requester": self.node_id,
            },
        )

    async def _request_chain(self, peer_id: str) -> None:
        session = _ChainSyncSession()
        self._pending_sync[peer_id] = session
        from_height = self.chain_height + 1 if self.chain_height > 0 else 1
        try:
            await self._send_chain_request(peer_id, from_height)
            await asyncio.wait_for(
                session.done.wait(),
                timeout=self.settings.network.chain_sync_timeout_seconds,
            )
            if session.blocks:
                self._resolve_fork(session.blocks)
        except asyncio.TimeoutError:
            logger.warning("Chain sync timeout from peer %s", peer_id)
        finally:
            self._pending_sync.pop(peer_id, None)

    def _resolve_fork(self, remote_chain: list[Block]) -> None:
        if not remote_chain:
            return
        local = self.blockchain.chain
        candidates = [local, remote_chain] if local else [remote_chain]
        canonical = self.consensus.select_canonical_chain(
            candidates, genesis_stakes=self.genesis_stakes
        )
        if canonical and canonical != local:
            if self.blockchain.replace_chain(
                canonical, genesis_stakes=self.genesis_stakes
            ):
                self._persist_state()
                logger.info("Chain replaced: new height %s", len(canonical))

    async def _announce_hello(self) -> None:
        await self.p2p.broadcast(MessageType.HELLO, self._hello_payload())

    async def _send_hello(self, peer_id: str) -> None:
        await self.p2p.send_to_peer(peer_id, MessageType.HELLO, self._hello_payload())

    async def _handle_message(
        self, peer_id: str, msg_type: MessageType, payload: dict[str, Any]
    ) -> None:
        if msg_type == MessageType.HELLO:
            await self._on_hello(peer_id, payload)
        elif msg_type == MessageType.PEERS:
            self.discovery.add_peers(payload.get("peers", []))
            for url in self.discovery.known_peers[: self.settings.network.max_peers]:
                await self.connect_peer(url)
        elif msg_type == MessageType.GET_CHAIN:
            from_height = _resolve_get_chain_from_height(payload.get("from_height"))
            max_batch = self.settings.network.chain_sync_batch_size
            batch_size = _resolve_get_chain_batch_size(payload.get("limit"), max_batch)
            blocks = self.blockchain.get_blocks_from(from_height, limit=batch_size)
            next_height = from_height + len(blocks)
            total_height = self.chain_height
            has_more = len(blocks) == batch_size and next_height <= total_height
            await self.p2p.send_to_peer(
                peer_id,
                MessageType.CHAIN_RESPONSE,
                {
                    "blocks": blocks,
                    "from_height": from_height,
                    "next_height": next_height,
                    "has_more": has_more,
                    "node_id": self.node_id,
                },
            )
        elif msg_type == MessageType.CHAIN_RESPONSE:
            session = self._pending_sync.get(peer_id)
            if session is not None and not session.done.is_set():
                blocks = payload.get("blocks", [])
                session.blocks.extend(blocks)
                has_more = bool(payload.get("has_more", False))
                if has_more:
                    next_height = int(payload.get("next_height", 1))
                    await self._send_chain_request(peer_id, next_height)
                else:
                    session.done.set()
            else:
                self._resolve_fork(payload.get("blocks", []))
        elif msg_type == MessageType.NEW_BLOCK:
            block = payload.get("block")
            if block:
                added = self.blockchain.add_block(block)
                if added:
                    self._persist_state()
                    self._metrics.inc_blocks_accepted()
                    self._update_metrics()
                    logger.info("New block accepted: index %s", block.get("block_index"))
                else:
                    await self.sync_chain()
        elif msg_type == MessageType.PING:
            await self.p2p.send_to_peer(peer_id, MessageType.PONG, {"node_id": self.node_id})
        elif msg_type == MessageType.PONG:
            peer = self.p2p.peers.get(peer_id)
            if peer:
                peer.last_pong_at = time.monotonic()

    async def _on_hello(self, peer_id: str, payload: dict[str, Any]) -> None:
        peer = self.p2p.peers.get(peer_id)
        if peer is None:
            return

        if self.settings.network.peer_auth.enabled:
            if not verify_hello(payload, self.settings.network.peer_auth):
                logger.warning("HELLO signature verification failed for %s", peer_id)
                await peer.close()
                return

        remote_consensus = payload.get("consensus_type")
        if remote_consensus != self.settings.consensus.type:
            logger.warning(
                "Consensus mismatch with %s: %s vs %s",
                peer_id,
                remote_consensus,
                self.settings.consensus.type,
            )
            await peer.close()
            return

        local_genesis = genesis_hash(
            self.blockchain.chain, self.settings.genesis.prev_hash
        )
        remote_genesis = payload.get("genesis_hash")
        if remote_genesis != local_genesis:
            logger.warning(
                "Genesis hash mismatch with %s: %s vs %s",
                peer_id,
                remote_genesis,
                local_genesis,
            )
            await peer.close()
            return

        peer.mark_authenticated()
        if peer_id not in self._url_by_peer:
            await self._send_hello(peer_id)

        remote_height = int(payload.get("chain_height", 0))
        if remote_height > self.chain_height:
            await self._request_chain(peer_id)

    async def _ping_loop(self) -> None:
        while self._running:
            now = time.monotonic()
            pong_timeout = self.settings.network.pong_timeout_seconds
            for peer_id, peer in list(self.p2p.peers.items()):
                if peer.closed:
                    continue
                if (
                    peer.last_ping_at is not None
                    and peer.last_pong_at is not None
                    and peer.last_pong_at < peer.last_ping_at
                    and now - peer.last_ping_at > pong_timeout
                ):
                    logger.warning("PONG timeout for peer %s; closing", peer_id)
                    self._metrics.inc_pong_timeouts()
                    await peer.close()
                    continue
                peer.last_ping_at = now
            await self.p2p.broadcast(MessageType.PING, {"node_id": self.node_id})
            self._update_metrics()
            await asyncio.sleep(self.settings.network.ping_interval_seconds)

    async def _reconnect_loop(self) -> None:
        while self._running:
            targets = set(self.settings.network.bootstrap_peers) | set(
                self.discovery.known_peers
            )
            for url in sorted(targets):
                if url in self._active_urls or url == self.p2p.local_url:
                    continue
                if self._reconnect.should_retry(url):
                    await self.connect_peer(url)
            await asyncio.sleep(1.0)
