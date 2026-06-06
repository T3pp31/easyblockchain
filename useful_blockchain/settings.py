"""設定ファイルの読み込み。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from useful_blockchain.types import (
    AppSettings,
    ConsensusSettings,
    NetworkSettings,
    NodeSettings,
    PosSettings,
    PowSettings,
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default.yaml"


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


def _parse_network(data: dict[str, Any]) -> NetworkSettings:
    return NetworkSettings(
        host=str(data.get("host", "0.0.0.0")),
        port=int(data.get("port", 8765)),
        bootstrap_peers=list(data.get("bootstrap_peers", [])),
        mdns_enabled=bool(data.get("mdns_enabled", False)),
        mdns_service_name=str(data.get("mdns_service_name", "_easyblockchain._tcp.local.")),
        max_peers=int(data.get("max_peers", 25)),
        chain_sync_batch_size=int(data.get("chain_sync_batch_size", 100)),
        ping_interval_seconds=int(data.get("ping_interval_seconds", 30)),
        connection_timeout_seconds=int(data.get("connection_timeout_seconds", 10)),
    )


def _parse_node(data: dict[str, Any]) -> NodeSettings:
    return NodeSettings(
        data_dir=str(data.get("data_dir", "./data")),
        node_id=str(data.get("node_id", "")),
    )


def parse_settings(data: dict[str, Any]) -> AppSettings:
    return AppSettings(
        consensus=_parse_consensus(data.get("consensus", {})),
        network=_parse_network(data.get("network", {})),
        node=_parse_node(data.get("node", {})),
    )


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
