"""ブロックチェーン関連の型定義。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict


ConsensusType = Literal["pow", "pos"]
Environment = Literal["development", "production"]
LogFormat = Literal["text", "json"]

DEFAULT_GENESIS_PREV_HASH = "0" * 64


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
class TlsSettings:
    enabled: bool = False
    cert_file: str = ""
    key_file: str = ""
    ca_file: str = ""
    verify_peer: bool = False


@dataclass
class PeerAuthSettings:
    enabled: bool = True
    max_skew_seconds: int = 300


@dataclass
class RateLimitSettings:
    max_connections_per_ip_per_minute: int = 10
    max_messages_per_peer_per_second: int = 50
    max_decode_errors_before_disconnect: int = 5


@dataclass
class ReconnectSettings:
    enabled: bool = True
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    max_attempts: int = 0
    backoff_multiplier: float = 2.0


DEFAULT_BLOCKED_PEER_CIDRS: tuple[str, ...] = (
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
)


@dataclass
class PeerConnectSettings:
    allow_private_ips: bool = False
    blocked_cidrs: list[str] = field(
        default_factory=lambda: list(DEFAULT_BLOCKED_PEER_CIDRS)
    )
    max_peers_per_message: int = 50
    allowed_ports: list[int] = field(default_factory=lambda: [80, 443, 8765])


@dataclass
class NetworkSettings:
    host: str = "0.0.0.0"
    port: int = 8765
    bootstrap_peers: list[str] = field(default_factory=list)
    mdns_enabled: bool = False
    mdns_service_name: str = "_easyblockchain._tcp.local."
    max_peers: int = 25
    max_message_bytes: int = 1_048_576
    chain_sync_batch_size: int = 100
    ping_interval_seconds: int = 30
    connection_timeout_seconds: int = 10
    chain_sync_timeout_seconds: int = 10
    shutdown_peer_close_timeout_seconds: int = 2
    shutdown_server_wait_timeout_seconds: int = 3
    pong_timeout_seconds: int = 90
    tls: TlsSettings = field(default_factory=TlsSettings)
    peer_auth: PeerAuthSettings = field(default_factory=PeerAuthSettings)
    peer_connect: PeerConnectSettings = field(default_factory=PeerConnectSettings)
    rate_limit: RateLimitSettings = field(default_factory=RateLimitSettings)
    reconnect: ReconnectSettings = field(default_factory=ReconnectSettings)


@dataclass
class ObservabilitySettings:
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 9090
    log_format: LogFormat = "text"
    health_path: str = "/healthz"
    ready_path: str = "/readyz"
    metrics_path: str = "/metrics"
    min_peers_for_ready: int = 0
    auth_enabled: bool = False
    auth_token: str = ""


@dataclass
class NodeSettings:
    environment: Environment = "development"
    data_dir: str = "./data"
    node_id: str = ""
    log_level: str = "INFO"
    require_external_keys: bool = False


@dataclass
class PersistenceSettings:
    schema_version: int = 1
    max_chain_file_bytes: int = 67_108_864
    chain_file: str = "chain.json"
    meta_file: str = "meta.json"
    genesis_stakes_file: str = "genesis_stakes.json"
    keys_dir: str = "keys"
    private_key_file: str = "node.pem"
    p2p_identity_file: str = "p2p_identity.pem"
    store_keys_on_disk: bool = True


@dataclass
class GenesisSettings:
    prev_hash: str = DEFAULT_GENESIS_PREV_HASH


@dataclass
class AppSettings:
    consensus: ConsensusSettings = field(default_factory=ConsensusSettings)
    network: NetworkSettings = field(default_factory=NetworkSettings)
    node: NodeSettings = field(default_factory=NodeSettings)
    genesis: GenesisSettings = field(default_factory=GenesisSettings)
    persistence: PersistenceSettings = field(default_factory=PersistenceSettings)
    observability: ObservabilitySettings = field(default_factory=ObservabilitySettings)
