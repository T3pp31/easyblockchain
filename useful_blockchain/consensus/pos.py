"""Proof of Stake 合意実装。"""

from __future__ import annotations

import hashlib

from useful_blockchain.consensus.base import ConsensusProtocol
from useful_blockchain.hash_utils import calc_body_hash, calc_pos_tran_hash
from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import Block, PosSettings, ValidationResult


class ProofOfStake(ConsensusProtocol):
    def __init__(
        self,
        settings: PosSettings,
        node_validator_id: str | None = None,
        signature_manager: SignatureManager | None = None,
    ) -> None:
        self.settings = settings
        self.node_validator_id = node_validator_id
        self.signature_manager = signature_manager or SignatureManager()
        self.validators: dict[str, int] = {}
        self.validator_public_keys: dict[str, str] = {}

    @property
    def consensus_type(self) -> str:
        return "pos"

    def register_validator(
        self,
        validator_id: str,
        stake: int,
        public_key_pem: str | None = None,
    ) -> None:
        if stake < self.settings.min_stake:
            raise ValueError(
                f"Stake {stake} is below minimum {self.settings.min_stake}"
            )
        self.validators[validator_id] = stake
        if public_key_pem:
            self.validator_public_keys[validator_id] = public_key_pem
        elif self.node_validator_id == validator_id and self.signature_manager.public_key:
            self.validator_public_keys[validator_id] = (
                self.signature_manager.export_public_key().decode("utf-8")
            )

    def get_total_stake(self) -> int:
        return sum(self.validators.values())

    def select_proposer(self, slot: int) -> str:
        if not self.validators:
            raise ValueError("No validators registered")
        seed = hashlib.sha256(f"slot-{slot}".encode()).hexdigest()
        pick = int(seed, 16) % self.get_total_stake()
        cumulative = 0
        for validator_id, stake in sorted(self.validators.items()):
            cumulative += stake
            if pick < cumulative:
                return validator_id
        return sorted(self.validators.keys())[-1]

    def prepare_block(self, block: Block, chain: list[Block]) -> Block:
        slot = len(chain) + 1
        proposer = self.select_proposer(slot)
        if self.node_validator_id is None:
            raise ValueError("node_validator_id is not set")
        if proposer != self.node_validator_id:
            raise ValueError(f"Not proposer for slot {slot}: expected {proposer}")

        if self.signature_manager.private_key is None:
            raise ValueError("Private key required for PoS block proposal")

        header = block["block_header"]
        body_hash = calc_body_hash(block["tran_body"])
        header["validator_id"] = proposer
        header["slot"] = slot
        header["tran_hash"] = calc_pos_tran_hash(
            header["prev_hash"], body_hash, proposer, slot
        )
        header["consensus_type"] = "pos"

        signed = self.signature_manager.sign_block(dict(block))
        block.update(signed)
        return block

    def validate_block(self, block: Block, chain: list[Block]) -> ValidationResult:
        header = block.get("block_header", {})
        if header.get("consensus_type") != "pos":
            return ValidationResult(valid=False, reason="consensus_type is not pos")

        validator_id = header.get("validator_id")
        slot = header.get("slot")
        if not validator_id or slot is None:
            return ValidationResult(valid=False, reason="missing PoS fields")

        if validator_id not in self.validators:
            return ValidationResult(valid=False, reason="unknown validator")

        expected_proposer = self.select_proposer(int(slot))
        if validator_id != expected_proposer:
            return ValidationResult(valid=False, reason="invalid proposer for slot")

        body_hash = calc_body_hash(block["tran_body"])
        expected_hash = calc_pos_tran_hash(
            header["prev_hash"], body_hash, str(validator_id), int(slot)
        )
        if header["tran_hash"] != expected_hash:
            return ValidationResult(valid=False, reason="tran_hash mismatch")

        if "signature" not in block or "public_key" not in block:
            return ValidationResult(valid=False, reason="missing validator signature")

        if not self.signature_manager.verify_block_signature(block):
            return ValidationResult(valid=False, reason="invalid validator signature")

        return ValidationResult(valid=True)

    def on_block_added(self, block: Block) -> None:
        validator_id = block.get("block_header", {}).get("validator_id")
        if validator_id and validator_id in self.validators:
            self.validators[validator_id] += self.settings.block_reward

    def select_canonical_chain(self, chains: list[list[Block]]) -> list[Block]:
        valid_chains: list[list[Block]] = []
        for chain in chains:
            if self._is_chain_valid(chain):
                valid_chains.append(chain)
        if not valid_chains:
            return []
        return max(valid_chains, key=lambda c: (len(c), self._stake_weight(c)))

    def _stake_weight(self, chain: list[Block]) -> int:
        weight = 0
        for block in chain:
            validator_id = block.get("block_header", {}).get("validator_id")
            if validator_id and validator_id in self.validators:
                weight += self.validators[validator_id]
        return weight

    def _is_chain_valid(self, chain: list[Block]) -> bool:
        for index, block in enumerate(chain):
            previous = chain[index - 1] if index > 0 else None
            if previous is not None:
                link = self.validate_chain_link(block, previous)
                if not link.valid:
                    return False
            result = self.validate_block(block, chain[:index])
            if not result.valid:
                return False
        return True

    def score_chain(self, chain: list[Block]) -> tuple[int, int]:
        return len(chain), self._stake_weight(chain)

    def sync_validators_from_chain(self, chain: list[Block], genesis_stakes: dict[str, int]) -> None:
        """チェーン再生時にバリデータセットを復元する。"""
        self.validators = dict(genesis_stakes)
        temp = ProofOfStake(self.settings)
        temp.validators = dict(genesis_stakes)
        for block in chain:
            temp.on_block_added(block)
        self.validators = temp.validators
