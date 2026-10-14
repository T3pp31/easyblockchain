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

    @staticmethod
    def compute_validators_from_chain(
        chain: list[Block],
        genesis_stakes: dict[str, int],
        settings: PosSettings,
    ) -> dict[str, int]:
        """genesis_stakes とチェーン上の報酬から実行時ステークを導出する。"""
        validators = dict(genesis_stakes)
        for block in chain:
            ProofOfStake.apply_block_reward(validators, block, settings)
        return validators

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

    def get_total_stake(self, validators: dict[str, int] | None = None) -> int:
        stake_map = validators if validators is not None else self.validators
        return sum(stake_map.values())

    def select_proposer(
        self,
        slot: int,
        validators: dict[str, int] | None = None,
    ) -> str:
        stake_map = validators if validators is not None else self.validators
        if not stake_map:
            raise ValueError("No validators registered")
        seed = hashlib.sha256(f"slot-{slot}".encode()).hexdigest()
        pick = int(seed, 16) % self.get_total_stake(stake_map)
        cumulative = 0
        for validator_id, stake in sorted(stake_map.items()):
            cumulative += stake
            if pick < cumulative:
                return validator_id
        return sorted(stake_map.keys())[-1]

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

    @staticmethod
    def apply_block_reward(
        validators: dict[str, int], block: Block, settings: PosSettings
    ) -> None:
        """ブロックの報酬をバリデータ状態に適用する（報酬ルールの一元化）。"""
        validator_id = block.get("block_header", {}).get("validator_id")
        if validator_id and validator_id in validators:
            validators[validator_id] += settings.block_reward

    def validate_block(
        self,
        block: Block,
        chain: list[Block],
        *,
        validators_at_state: dict[str, int] | None = None,
        expected_height: int | None = None,
    ) -> ValidationResult:
        """単一ブロックが PoS ルールを満たすか検証する。

        expected_height 未指定時は chain を先行ブロック列として扱う。
        ブロック検証時のステーク状態は validators_at_state で明示的に渡す。
        validators_at_state / self.validators を変更しない。
        """
        validators = (
            validators_at_state if validators_at_state is not None else self.validators
        )
        header = block.get("block_header", {})
        if header.get("consensus_type") != "pos":
            return ValidationResult(valid=False, reason="consensus_type is not pos")

        validator_id = header.get("validator_id")
        slot = header.get("slot")
        if (
            not validator_id
            or not isinstance(slot, int)
            or isinstance(slot, bool)
            or slot < 0
        ):
            return ValidationResult(valid=False, reason="missing PoS fields")

        if not validators:
            return ValidationResult(valid=False, reason="no validators registered")

        if slot != (len(chain) + 1 if expected_height is None else expected_height):
            return ValidationResult(
                valid=False, reason="slot does not match block height"
            )

        if validator_id not in validators:
            return ValidationResult(valid=False, reason="unknown validator")

        tran_body = block.get("tran_body")
        prev_hash = header.get("prev_hash")
        tran_hash = header.get("tran_hash")
        if (
            not isinstance(tran_body, dict)
            or not isinstance(prev_hash, str)
            or tran_hash is None
        ):
            return ValidationResult(valid=False, reason="missing PoS fields")

        expected_proposer = self.select_proposer(slot, validators)
        if validator_id != expected_proposer:
            return ValidationResult(valid=False, reason="invalid proposer for slot")

        body_hash = calc_body_hash(tran_body)
        expected_hash = calc_pos_tran_hash(
            prev_hash, body_hash, str(validator_id), slot
        )
        if tran_hash != expected_hash:
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

    def select_canonical_chain(
        self,
        chains: list[list[Block]],
        *,
        genesis_stakes: dict[str, int] | None = None,
    ) -> list[Block]:
        """複数チェーンから正規チェーンを選択する。

        有効なチェーンの中から (チェーン長, ステーク重み, チップハッシュ)
        の辞書順で最大のものを選ぶ。チップハッシュによる最終タイブレークで、
        同長・同重みのチェーン間でも到着順に依存しない決定的な選択を行う。
        チップハッシュまで完全に同点のチェーン（同一チップ、または
        tran_hash 欠落で空文字に揃う場合）では最初の候補が選ばれる。
        """
        valid_chains: list[list[Block]] = []
        for chain in chains:
            if genesis_stakes is not None:
                is_valid = self.validate_chain_with_genesis_stakes(chain, genesis_stakes)
            elif self._is_chain_valid(chain):
                is_valid = True
            else:
                is_valid = False
            if is_valid:
                valid_chains.append(chain)
        if not valid_chains:
            return []

        def score(chain: list[Block]) -> tuple[int, int, str]:
            tip_hash = str(
                (chain[-1].get("block_header") or {}).get("tran_hash", "")
            ) if chain else ""
            if genesis_stakes is not None:
                end_validators = self.compute_validators_from_chain(
                    chain, genesis_stakes, self.settings
                )
                return len(chain), self._stake_weight(chain, end_validators), tip_hash
            return len(chain), self._stake_weight(chain), tip_hash

        return max(valid_chains, key=score)

    def _stake_weight(
        self,
        chain: list[Block],
        validators: dict[str, int] | None = None,
    ) -> int:
        stake_map = validators if validators is not None else self.validators
        weight = 0
        for block in chain:
            validator_id = (block.get("block_header") or {}).get("validator_id")
            if validator_id and validator_id in stake_map:
                weight += stake_map[validator_id]
        return weight

    def _is_chain_valid(self, chain: list[Block]) -> bool:
        for index, block in enumerate(chain):
            previous = chain[index - 1] if index > 0 else None
            link = self.validate_chain_link(block, previous, self.genesis_prev_hash)
            if not link.valid:
                return False
            result = self.validate_block(block, chain[:index])
            if not result.valid:
                return False
        return True

    def validate_chain_with_genesis_stakes(
        self,
        chain: list[Block],
        genesis_stakes: dict[str, int],
        genesis_prev_hash: str | None = None,
    ) -> bool:
        expected_genesis = genesis_prev_hash or self.genesis_prev_hash
        validators = dict(genesis_stakes)
        for index, block in enumerate(chain):
            previous = chain[index - 1] if index > 0 else None
            link = self.validate_chain_link(block, previous, expected_genesis)
            if not link.valid:
                return False
            result = self.validate_block(
                block,
                chain,
                validators_at_state=validators,
                expected_height=index + 1,
            )
            if not result.valid:
                return False
            self.apply_block_reward(validators, block, self.settings)
        return True

    def score_chain(self, chain: list[Block]) -> tuple[int, int]:
        return len(chain), self._stake_weight(chain)

    def sync_validators_from_chain(
        self, chain: list[Block], genesis_stakes: dict[str, int]
    ) -> None:
        """チェーン再生時にバリデータセットを復元する。"""
        self.validators = self.compute_validators_from_chain(
            chain, genesis_stakes, self.settings
        )
