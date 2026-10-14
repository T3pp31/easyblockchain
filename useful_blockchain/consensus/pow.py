"""Proof of Work 合意実装。"""

from __future__ import annotations

import datetime as dt
import math

from useful_blockchain.consensus.base import ConsensusProtocol
from useful_blockchain.hash_utils import (
    calc_body_hash,
    calc_pow_tran_hash,
    meets_difficulty,
)
from useful_blockchain.types import Block, PowSettings, ValidationResult


class ProofOfWork(ConsensusProtocol):
    def __init__(self, settings: PowSettings) -> None:
        self.settings = settings

    @property
    def consensus_type(self) -> str:
        return "pow"

    def get_difficulty(self, chain: list[Block]) -> int:
        if not chain:
            return self.settings.initial_difficulty

        interval = self.settings.adjustment_interval
        if len(chain) < interval:
            last = chain[-1]["block_header"]
            return int(last.get("difficulty", self.settings.initial_difficulty))

        recent = chain[-interval:]
        first_difficulty = int(
            recent[0]["block_header"].get("difficulty", self.settings.initial_difficulty)
        )
        actual_time = self._elapsed_seconds(recent[0], recent[-1])
        expected_time = self.settings.target_block_time_seconds * (interval - 1)
        if expected_time <= 0 or actual_time <= 0:
            return first_difficulty

        ratio = actual_time / expected_time
        new_difficulty = first_difficulty
        if ratio > 1.0:
            factor = min(ratio, self.settings.max_adjustment_factor)
            new_difficulty = max(1, int(first_difficulty / factor))
            # int() の切り捨てで低下幅度が max_adjustment_factor を超えないよう下側クランプ
            lower_bound = math.ceil(
                first_difficulty / self.settings.max_adjustment_factor
            )
            new_difficulty = max(new_difficulty, lower_bound)
        elif ratio < 1.0:
            divisor = max(ratio, 1 / self.settings.max_adjustment_factor)
            new_difficulty = max(1, int(first_difficulty / divisor))
        return new_difficulty

    def _elapsed_seconds(self, start_block: Block, end_block: Block) -> int:
        fallback = self.settings.target_block_time_seconds * self.settings.adjustment_interval
        start_item = start_block.get("block_item")
        end_item = end_block.get("block_item")
        if not isinstance(start_item, str) or not isinstance(end_item, str):
            return fallback
        try:
            start = dt.datetime.strptime(start_item, "%Y-%m-%d %H:%M:%S")
            end = dt.datetime.strptime(end_item, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return fallback
        return max(1, int((end - start).total_seconds()))

    def mine_block(self, block: Block, chain: list[Block]) -> Block:
        header = block["block_header"]
        prev_hash = header["prev_hash"]
        body_hash = calc_body_hash(block["tran_body"])
        difficulty = self.get_difficulty(chain)

        for nonce in range(self.settings.max_mining_iterations):
            tran_hash = calc_pow_tran_hash(prev_hash, body_hash, nonce)
            if meets_difficulty(tran_hash, difficulty):
                header["nonce"] = nonce
                header["difficulty"] = difficulty
                header["tran_hash"] = tran_hash
                header["consensus_type"] = "pow"
                return block
        raise RuntimeError("PoW mining failed: max iterations exceeded")

    def prepare_block(self, block: Block, chain: list[Block]) -> Block:
        return self.mine_block(block, chain)

    def validate_block(self, block: Block, chain: list[Block]) -> ValidationResult:
        """単一ブロックが PoW ルールを満たすか検証する。

        chain は検証対象ブロックを**含まない**親チェーンであり、
        期待難易度はそのチェーンから計算される。
        """
        header = block.get("block_header", {})
        if header.get("consensus_type") != "pow":
            return ValidationResult(valid=False, reason="consensus_type is not pow")
        missing_fields = [
            field_name
            for field_name, container in (
                ("nonce", header),
                ("difficulty", header),
                ("tran_body", block),
                ("prev_hash", header),
                ("tran_hash", header),
            )
            if field_name not in container
        ]
        if missing_fields:
            return ValidationResult(
                valid=False,
                reason=f"missing PoW fields: {', '.join(missing_fields)}",
            )

        try:
            declared_difficulty = int(header["difficulty"])
        except (TypeError, ValueError):
            return ValidationResult(valid=False, reason="invalid difficulty")
        try:
            nonce = int(header["nonce"])
        except (TypeError, ValueError):
            return ValidationResult(valid=False, reason="invalid nonce")

        expected_difficulty = self.get_difficulty(chain)
        if declared_difficulty != expected_difficulty:
            return ValidationResult(
                valid=False,
                reason="difficulty does not match network expectation",
            )

        block_item = block.get("block_item")
        if not isinstance(block_item, str):
            return ValidationResult(valid=False, reason="missing or invalid block_item")
        try:
            block_time = dt.datetime.strptime(block_item, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ValidationResult(valid=False, reason="invalid block_item format")
        if chain:
            parent_item = chain[-1].get("block_item")
            parent_time = None
            if isinstance(parent_item, str):
                try:
                    parent_time = dt.datetime.strptime(parent_item, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    parent_time = None
            if parent_time is None:
                # 親の block_item が不正な場合は単調性を検証できないため fail-closed
                return ValidationResult(
                    valid=False, reason="parent block_item missing or invalid"
                )
            if block_time < parent_time:
                return ValidationResult(
                    valid=False, reason="block_item earlier than parent"
                )

        body_hash = calc_body_hash(block["tran_body"])
        expected_hash = calc_pow_tran_hash(
            header["prev_hash"], body_hash, nonce
        )
        if header["tran_hash"] != expected_hash:
            return ValidationResult(valid=False, reason="tran_hash mismatch")
        if not meets_difficulty(expected_hash, declared_difficulty):
            return ValidationResult(valid=False, reason="difficulty not met")
        return ValidationResult(valid=True)

    def select_canonical_chain(
        self,
        chains: list[list[Block]],
        *,
        genesis_stakes: dict[str, int] | None = None,
    ) -> list[Block]:
        valid_chains: list[list[Block]] = []
        for chain in chains:
            if self._is_chain_valid(chain):
                valid_chains.append(chain)
        if not valid_chains:
            return []
        return max(valid_chains, key=lambda c: (len(c), self._total_difficulty(c)))

    def _total_difficulty(self, chain: list[Block]) -> int:
        return sum(int(b["block_header"].get("difficulty", 0)) for b in chain)

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

    def score_chain(self, chain: list[Block]) -> tuple[int, int]:
        return len(chain), self._total_difficulty(chain)
