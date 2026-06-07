"""ノードオーケストレータ。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from useful_blockchain.blockchain import BlockChain
from useful_blockchain.consensus.factory import create_consensus
from useful_blockchain.hash_utils import genesis_hash
from useful_blockchain.network.discovery import PeerDiscovery
from useful_blockchain.network.messages import MessageType
from useful_blockchain.network.server import P2PServer
from useful_blockchain.persistence import ChainStore, ChainStoreError, PersistedState
from useful_blockchain.settings import load_settings_with_overrides
from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import Block

logger = logging.getLogger(__name__)


class Node:
    def __init__(
        self,
        config_path: str | Path | None = None,
        overrides: dict[str, Any] | None = None,
        genesis_stakes: dict[str, int] | None = None,
    ) -> None:
        self.settings = load_settings_with_overrides(config_path, overrides)
        self._data_dir = Path(self.settings.node.data_dir)
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

        self.signature_manager = SignatureManager()
        if self.settings.consensus.type == "pos":
            if persisted is not None and persisted.private_key_pem is not None:
                self.signature_manager.import_private_key(persisted.private_key_pem)
            else:
                self.signature_manager.generate_key_pair()
            self.enable_signature = True
        else:
            self.enable_signature = False

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
        elif self.settings.consensus.type == "pos":
            self._persist_state()

        self._pending_sync: dict[str, asyncio.Future[list[Block]]] = {}
        self._connected_urls: set[str] = set()
        self.p2p = P2PServer(self.settings.network, self.node_id, self._handle_message)
        self.discovery = PeerDiscovery(self.settings.network, self.p2p.local_url)
        self._running = False
        self._ping_task: asyncio.Task[None] | None = None

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
        if self.settings.consensus.type == "pos" and self.signature_manager.private_key:
            private_key_pem = self.signature_manager.export_private_key()

        state = PersistedState(
            chain=list(self.blockchain.chain),
            node_id=self.node_id,
            genesis_prev_hash=self.settings.genesis.prev_hash,
            genesis_stakes=dict(self.genesis_stakes),
            private_key_pem=private_key_pem,
        )
        try:
            self._store.save(self._data_dir, state)
        except ChainStoreError:
            logger.exception("Failed to persist state to %s", self._data_dir)
            raise

    @property
    def chain_height(self) -> int:
        return len(self.blockchain.chain)

    async def start(self) -> None:
        await self.p2p.start()

        def _on_peer_found(url: str) -> None:
            asyncio.create_task(self.connect_peer(url))

        self.discovery.start_mdns(on_peer_found=_on_peer_found)
        for peer_url in self.discovery.known_peers:
            await self.connect_peer(peer_url)
        self._running = True
        self._ping_task = asyncio.create_task(self._ping_loop())
        await self._announce_hello()

    async def stop(self) -> None:
        self._running = False
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        self.discovery.stop_mdns()
        await self.p2p.stop()
        self._persist_state()

    async def connect_peer(self, url: str) -> None:
        if not url or url == self.p2p.local_url or url in self._connected_urls:
            return
        peer_id = await self.p2p.connect_peer(url)
        if peer_id:
            self._connected_urls.add(url)
            await self._send_hello(peer_id)
            await self.p2p.send_to_peer(
                peer_id,
                MessageType.PEERS,
                {"peers": self.discovery.known_peers + [self.p2p.local_url]},
            )

    async def add_block(self, input_data: Any, output_data: Any) -> Block:
        block = self.blockchain.add_new_block(input_data, output_data)
        self._persist_state()
        await self.p2p.broadcast(
            MessageType.NEW_BLOCK,
            {"block": block, "node_id": self.node_id},
        )
        return block

    async def sync_chain(self) -> None:
        for peer_id in list(self.p2p.peers.keys()):
            await self._request_chain(peer_id)

    async def _request_chain(self, peer_id: str) -> None:
        future: asyncio.Future[list[Block]] = asyncio.get_running_loop().create_future()
        self._pending_sync[peer_id] = future
        await self.p2p.send_to_peer(
            peer_id,
            MessageType.GET_CHAIN,
            {"from_height": 1, "requester": self.node_id},
        )
        try:
            remote_chain = await asyncio.wait_for(future, timeout=10.0)
            self._resolve_fork(remote_chain)
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
        await self.p2p.broadcast(
            MessageType.HELLO,
            {
                "node_id": self.node_id,
                "consensus_type": self.settings.consensus.type,
                "chain_height": self.chain_height,
                "genesis_hash": genesis_hash(
                    self.blockchain.chain, self.settings.genesis.prev_hash
                ),
            },
        )

    async def _send_hello(self, peer_id: str) -> None:
        await self.p2p.send_to_peer(
            peer_id,
            MessageType.HELLO,
            {
                "node_id": self.node_id,
                "consensus_type": self.settings.consensus.type,
                "chain_height": self.chain_height,
                "genesis_hash": genesis_hash(
                    self.blockchain.chain, self.settings.genesis.prev_hash
                ),
            },
        )

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
            blocks = self.blockchain.get_blocks_from(int(payload.get("from_height", 1)))
            await self.p2p.send_to_peer(
                peer_id,
                MessageType.CHAIN_RESPONSE,
                {"blocks": blocks, "node_id": self.node_id},
            )
        elif msg_type == MessageType.CHAIN_RESPONSE:
            future = self._pending_sync.get(peer_id)
            if future and not future.done():
                blocks = payload.get("blocks", [])
                future.set_result(blocks)
            else:
                self._resolve_fork(payload.get("blocks", []))
        elif msg_type == MessageType.NEW_BLOCK:
            block = payload.get("block")
            if block:
                added = self.blockchain.add_block(block)
                if added:
                    self._persist_state()
                    logger.info("New block accepted: index %s", block.get("block_index"))
                else:
                    await self.sync_chain()
        elif msg_type == MessageType.PING:
            await self.p2p.send_to_peer(peer_id, MessageType.PONG, {"node_id": self.node_id})
        elif msg_type == MessageType.PONG:
            pass

    async def _on_hello(self, peer_id: str, payload: dict[str, Any]) -> None:
        remote_consensus = payload.get("consensus_type")
        if remote_consensus != self.settings.consensus.type:
            logger.warning(
                "Consensus mismatch with %s: %s vs %s",
                peer_id,
                remote_consensus,
                self.settings.consensus.type,
            )
            peer = self.p2p.peers.get(peer_id)
            if peer:
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
            peer = self.p2p.peers.get(peer_id)
            if peer:
                await peer.close()
            return
        remote_height = int(payload.get("chain_height", 0))
        if remote_height > self.chain_height:
            await self._request_chain(peer_id)

    async def _ping_loop(self) -> None:
        while self._running:
            await self.p2p.broadcast(MessageType.PING, {"node_id": self.node_id})
            await asyncio.sleep(self.settings.network.ping_interval_seconds)
