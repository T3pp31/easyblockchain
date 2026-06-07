"""合意プロトコルファクトリ。"""

from __future__ import annotations

from useful_blockchain.consensus.base import ConsensusProtocol
from useful_blockchain.consensus.pos import ProofOfStake
from useful_blockchain.consensus.pow import ProofOfWork
from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import AppSettings, ConsensusType


def create_consensus(
    settings: AppSettings,
    node_validator_id: str | None = None,
    signature_manager: SignatureManager | None = None,
    genesis_stakes: dict[str, int] | None = None,
) -> ConsensusProtocol:
    consensus_type: ConsensusType = settings.consensus.type
    if consensus_type == "pow":
        consensus: ConsensusProtocol = ProofOfWork(settings.consensus.pow)
    elif consensus_type == "pos":
        pos = ProofOfStake(
            settings.consensus.pos,
            node_validator_id=node_validator_id,
            signature_manager=signature_manager,
            genesis_stakes=genesis_stakes,
        )
        stakes = genesis_stakes or {}
        if node_validator_id and node_validator_id not in stakes:
            stakes[node_validator_id] = settings.consensus.pos.min_stake
        for validator_id, stake in stakes.items():
            pos.register_validator(validator_id, stake)
        consensus = pos
    else:
        raise ValueError(f"Unsupported consensus type: {consensus_type}")
    consensus.genesis_prev_hash = settings.genesis.prev_hash
    return consensus
