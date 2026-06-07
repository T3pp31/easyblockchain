"""設定ファイルの読み込み。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast

import yaml

from useful_blockchain.network.tls import validate_production_network
from useful_blockchain.types import (
    AppSettings,
    ConsensusSettings,
    DEFAULT_GENESIS_PREV_HASH,
    Environment,
    GenesisSettings,
    LogFormat,
    NetworkSettings,
    NodeSettings,
    ObservabilitySettings,
    PeerAuthSettings,
    PeerConnectSettings,
    PersistenceSettings,
    PosSettings,
    PowSettings,
    RateLimitSettings,
    ReconnectSettings,
    TlsSettings,
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default.yaml"

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_VALID_LOG_FORMATS = frozenset({"text", "json"})
_VALID_ENVIRONMENTS = frozenset({"development", "production"})


def resolve_log_level(name: str) -> int:
    normalized = name.strip().upper()
    if normalized not in _VALID_LOG_LEVELS:
        valid = ", ".join(sorted(_VALID_LOG_LEVELS))
        raise ValueError(f"Unsupported log level: {name!r}. Must be one of: {valid}")
    level = getattr(logging, normalized)
    if not isinstance(level, int):
        raise ValueError(f"Unsupported log level: {name!r}. Must be one of: {valid}")
    return level


def resolve_log_format(name: str) -> LogFormat:
    normalized = name.strip().lower()
    if normalized not in _VALID_LOG_FORMATS:
        valid = ", ".join(sorted(_VALID_LOG_FORMATS))
        raise ValueError(f"Unsupported log format: {name!r}. Must be one of: {valid}")
    return cast(LogFormat, normalized)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    return data if isinstance(data, dict) else {}


def _parse_pow(data: dict[str, Any]) -> PowSettings:
    return PowSettings(
        initial_difficulty=int(data.get("initial_difficulty", 4)),
        adjustment_interval=int(data.get("adjustment_interval", 10)),
        max_adjustment_factor=float(data.get("max_adjustment_factor", 2.0)),
        max_mining_iterations=int(data.get("max_mining_iterations", 1_000_000)),
        target_block_time_seconds=int(data.get("target_block_time_seconds", 10)),
    )


def _parse_pos(data: dict[str, Any]) -> PosSettings:
    return PosSettings(
        epoch_length=int(data.get("epoch_length", 10)),
        min_stake=int(data.get("min_stake", 100)),
        block_reward=int(data.get("block_reward", 10)),
    )


def _parse_consensus(data: dict[str, Any]) -> ConsensusSettings:
    consensus_type = str(data.get("type", "pow")).lower()
    if consensus_type not in ("pow", "pos"):
        raise ValueError(f"Unsupported consensus type: {consensus_type}")
    return ConsensusSettings(
        type=consensus_type,  # type: ignore[arg-type]
        pow=_parse_pow(data.get("pow", {})),
        pos=_parse_pos(data.get("pos", {})),
    )


def _parse_tls(data: dict[str, Any]) -> TlsSettings:
    return TlsSettings(
        enabled=bool(data.get("enabled", False)),
        cert_file=str(data.get("cert_file", "")),
        key_file=str(data.get("key_file", "")),
        ca_file=str(data.get("ca_file", "")),
        verify_peer=bool(data.get("verify_peer", False)),
    )


def _parse_peer_auth(data: dict[str, Any]) -> PeerAuthSettings:
    return PeerAuthSettings(
        enabled=bool(data.get("enabled", True)),
        max_skew_seconds=int(data.get("max_skew_seconds", 300)),
    )


def _parse_rate_limit(data: dict[str, Any]) -> RateLimitSettings:
    return RateLimitSettings(
        max_connections_per_ip_per_minute=int(
            data.get("max_connections_per_ip_per_minute", 10)
        ),
        max_messages_per_peer_per_second=int(
            data.get("max_messages_per_peer_per_second", 50)
        ),
        max_decode_errors_before_disconnect=int(
            data.get("max_decode_errors_before_disconnect", 5)
        ),
    )


def _parse_peer_connect(data: dict[str, Any]) -> PeerConnectSettings:
    blocked_cidrs = data.get("blocked_cidrs")
    if blocked_cidrs is None:
        blocked = list(PeerConnectSettings().blocked_cidrs)
    else:
        if not isinstance(blocked_cidrs, list):
            raise ValueError("network.peer_connect.blocked_cidrs must be a list")
        blocked = [str(cidr) for cidr in blocked_cidrs]
    return PeerConnectSettings(
        allow_private_ips=bool(data.get("allow_private_ips", False)),
        blocked_cidrs=blocked,
        max_peers_per_message=int(data.get("max_peers_per_message", 50)),
    )


def _parse_reconnect(data: dict[str, Any]) -> ReconnectSettings:
    return ReconnectSettings(
        enabled=bool(data.get("enabled", True)),
        initial_delay_seconds=float(data.get("initial_delay_seconds", 1.0)),
        max_delay_seconds=float(data.get("max_delay_seconds", 60.0)),
        max_attempts=int(data.get("max_attempts", 0)),
        backoff_multiplier=float(data.get("backoff_multiplier", 2.0)),
    )


def _parse_network(data: dict[str, Any]) -> NetworkSettings:
    return NetworkSettings(
        host=str(data.get("host", "0.0.0.0")),
        port=int(data.get("port", 8765)),
        bootstrap_peers=list(data.get("bootstrap_peers", [])),
        mdns_enabled=bool(data.get("mdns_enabled", False)),
        mdns_service_name=str(data.get("mdns_service_name", "_easyblockchain._tcp.local.")),
        max_peers=int(data.get("max_peers", 25)),
        max_message_bytes=int(data.get("max_message_bytes", 1_048_576)),
        chain_sync_batch_size=int(data.get("chain_sync_batch_size", 100)),
        ping_interval_seconds=int(data.get("ping_interval_seconds", 30)),
        connection_timeout_seconds=int(data.get("connection_timeout_seconds", 10)),
        chain_sync_timeout_seconds=int(data.get("chain_sync_timeout_seconds", 10)),
        shutdown_peer_close_timeout_seconds=int(
            data.get("shutdown_peer_close_timeout_seconds", 2)
        ),
        shutdown_server_wait_timeout_seconds=int(
            data.get("shutdown_server_wait_timeout_seconds", 3)
        ),
        pong_timeout_seconds=int(data.get("pong_timeout_seconds", 90)),
        tls=_parse_tls(data.get("tls", {})),
        peer_auth=_parse_peer_auth(data.get("peer_auth", {})),
        peer_connect=_parse_peer_connect(data.get("peer_connect", {})),
        rate_limit=_parse_rate_limit(data.get("rate_limit", {})),
        reconnect=_parse_reconnect(data.get("reconnect", {})),
    )


def _parse_environment(name: str) -> Environment:
    normalized = name.strip().lower()
    if normalized not in _VALID_ENVIRONMENTS:
        valid = ", ".join(sorted(_VALID_ENVIRONMENTS))
        raise ValueError(f"Unsupported environment: {name!r}. Must be one of: {valid}")
    return cast(Environment, normalized)


def _parse_safe_basename(value: str, default: str, field: str) -> str:
    name = str(value or default)
    if not name or name in (".", ".."):
        raise ValueError(f"Invalid {field}: {name!r}")
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError(f"Invalid {field}: {name!r} (must be a single path component)")
    return name


def _normalize_data_dir(value: str) -> str:
    return str(Path(str(value or "./data")).expanduser().resolve(strict=False))


def _parse_node(data: dict[str, Any]) -> NodeSettings:
    log_level = str(data.get("log_level", "INFO"))
    resolve_log_level(log_level)
    environment = _parse_environment(str(data.get("environment", "development")))
    return NodeSettings(
        environment=environment,
        data_dir=_normalize_data_dir(str(data.get("data_dir", "./data"))),
        node_id=str(data.get("node_id", "")),
        log_level=log_level,
    )


def _parse_persistence(data: dict[str, Any]) -> PersistenceSettings:
    return PersistenceSettings(
        schema_version=int(data.get("schema_version", 1)),
        chain_file=_parse_safe_basename(
            str(data.get("chain_file", "chain.json")), "chain.json", "persistence.chain_file"
        ),
        meta_file=_parse_safe_basename(
            str(data.get("meta_file", "meta.json")), "meta.json", "persistence.meta_file"
        ),
        genesis_stakes_file=_parse_safe_basename(
            str(data.get("genesis_stakes_file", "genesis_stakes.json")),
            "genesis_stakes.json",
            "persistence.genesis_stakes_file",
        ),
        keys_dir=_parse_safe_basename(
            str(data.get("keys_dir", "keys")), "keys", "persistence.keys_dir"
        ),
        private_key_file=_parse_safe_basename(
            str(data.get("private_key_file", "node.pem")),
            "node.pem",
            "persistence.private_key_file",
        ),
        p2p_identity_file=_parse_safe_basename(
            str(data.get("p2p_identity_file", "p2p_identity.pem")),
            "p2p_identity.pem",
            "persistence.p2p_identity_file",
        ),
    )


def _parse_observability(data: dict[str, Any]) -> ObservabilitySettings:
    log_format = resolve_log_format(str(data.get("log_format", "text")))
    auth_enabled = bool(data.get("auth_enabled", False))
    auth_token = os.environ.get("EASYBLOCKCHAIN_OBSERVABILITY_TOKEN") or str(
        data.get("auth_token", "")
    )
    if auth_enabled and not auth_token:
        raise ValueError(
            "observability.auth_enabled requires a non-empty auth_token "
            "or EASYBLOCKCHAIN_OBSERVABILITY_TOKEN"
        )
    return ObservabilitySettings(
        enabled=bool(data.get("enabled", False)),
        host=str(data.get("host", "0.0.0.0")),
        port=int(data.get("port", 9090)),
        log_format=log_format,
        health_path=str(data.get("health_path", "/healthz")),
        ready_path=str(data.get("ready_path", "/readyz")),
        metrics_path=str(data.get("metrics_path", "/metrics")),
        min_peers_for_ready=int(data.get("min_peers_for_ready", 0)),
        auth_enabled=auth_enabled,
        auth_token=auth_token,
    )


def _parse_genesis(data: dict[str, Any]) -> GenesisSettings:
    prev_hash = str(data.get("prev_hash", DEFAULT_GENESIS_PREV_HASH)).lower()
    if len(prev_hash) != 64:
        raise ValueError("genesis.prev_hash must be a 64-character hex string")
    if not all(c in "0123456789abcdef" for c in prev_hash):
        raise ValueError("genesis.prev_hash must be a 64-character hex string")
    return GenesisSettings(prev_hash=prev_hash)


def parse_settings(data: dict[str, Any]) -> AppSettings:
    network = _parse_network(data.get("network", {}))
    node = _parse_node(data.get("node", {}))
    settings = AppSettings(
        consensus=_parse_consensus(data.get("consensus", {})),
        network=network,
        node=node,
        genesis=_parse_genesis(data.get("genesis", {})),
        persistence=_parse_persistence(data.get("persistence", {})),
        observability=_parse_observability(data.get("observability", {})),
    )
    validate_production_network(settings.node, settings.network)
    return settings


def load_settings(config_path: str | Path | None = None) -> AppSettings:
    env_path = os.environ.get("EASYBLOCKCHAIN_CONFIG")
    path = Path(config_path or env_path or DEFAULT_CONFIG_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    raw = load_yaml_config(path)
    return parse_settings(raw)


def load_settings_with_overrides(
    config_path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> AppSettings:
    env_path = os.environ.get("EASYBLOCKCHAIN_CONFIG")
    path = Path(config_path or env_path or DEFAULT_CONFIG_PATH)
    raw: dict[str, Any] = {}
    if path.exists():
        raw = load_yaml_config(path)
    if overrides:
        raw = _deep_merge(raw, overrides)
    return parse_settings(raw)
