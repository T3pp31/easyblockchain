"""合意プロトコルの抽象基底クラス。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from useful_blockchain.types import Block, ValidationResult


class ConsensusProtocol(ABC):
    @property
    @abstractmethod
    def consensus_type(self) -> str:
        ...

    @abstractmethod
    def prepare_block(self, block: Block, chain: list[Block]) -> Block:
        """ブロックに合意要件（マイニング・提案者署名等）を適用する。"""

    @abstractmethod
    def validate_block(self, block: Block, chain: list[Block]) -> ValidationResult:
        """単一ブロックが合意ルールを満たすか検証する。"""

    @abstractmethod
    def select_canonical_chain(self, chains: list[list[Block]]) -> list[Block]:
        """複数チェーンから正規チェーンを選択する。"""

    def on_block_added(self, block: Block) -> None:
        """ブロック追加後のフック（PoS 報酬等）。"""

    def validate_chain_link(self, block: Block, previous_block: Block | None) -> ValidationResult:
        if previous_block is None:
            return ValidationResult(valid=True)
        prev_tran = previous_block["block_header"]["tran_hash"]
        if block["block_header"]["prev_hash"] != prev_tran:
            return ValidationResult(valid=False, reason="prev_hash mismatch")
        if block["block_index"] != previous_block["block_index"] + 1:
            return ValidationResult(valid=False, reason="block_index mismatch")
        return ValidationResult(valid=True)

    def score_chain(self, chain: list[Block]) -> tuple[int, int]:
        """フォーク選択用スコア: (長さ, 重み)。"""
        return len(chain), 0
