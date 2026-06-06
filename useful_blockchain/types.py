"""ブロックチェーン関連の型定義。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict


ConsensusType = Literal["pow", "pos"]


class TransactionBody(TypedDict):
    input_data: Any
    output_data: Any


class BlockHeader(TypedDict, total=False):
    prev_hash: str
    tran_hash: str
    consensus_type: ConsensusType
    nonce: int
    difficulty: int
    validator_id: str
    slot: int


class Block(TypedDict, total=False):
    block_index: int
    block_item: str
    block_header: BlockHeader
    tran_counter: int
    tran_body: TransactionBody
    signature: str
    public_key: str


@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""


@dataclass
class ChainVerificationResult:
    valid: bool
    failed_at_index: int | None = None
    reason: str = ""


@dataclass
class PowSettings:
    initial_difficulty: int = 4
    adjustment_interval: int = 10
    max_adjustment_factor: float = 2.0
    max_mining_iterations: int = 1_000_000
    target_block_time_seconds: int = 10


@dataclass
class PosSettings:
    epoch_length: int = 10
    min_stake: int = 100
    block_reward: int = 10


@dataclass
class ConsensusSettings:
    type: ConsensusType = "pow"
    pow: PowSettings = field(default_factory=PowSettings)
    pos: PosSettings = field(default_factory=PosSettings)


@dataclass
class NetworkSettings:
    host: str = "0.0.0.0"
    port: int = 8765
    bootstrap_peers: list[str] = field(default_factory=list)
    mdns_enabled: bool = False
    mdns_service_name: str = "_easyblockchain._tcp.local."
    max_peers: int = 25
    chain_sync_batch_size: int = 100
    ping_interval_seconds: int = 30
    connection_timeout_seconds: int = 10


@dataclass
class NodeSettings:
    data_dir: str = "./data"
    node_id: str = ""


@dataclass
class AppSettings:
    consensus: ConsensusSettings = field(default_factory=ConsensusSettings)
    network: NetworkSettings = field(default_factory=NetworkSettings)
    node: NodeSettings = field(default_factory=NodeSettings)
