"""
シンプルなブロックチェーンの実装

このモジュールは基本的なブロックチェーンの機能を提供します。
各ブロックは前のブロックのハッシュ値を含んでおり、チェーン状に連結されています。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from useful_blockchain.chain_validator import verify_chain_integrity
from useful_blockchain.consensus.base import ConsensusProtocol
from useful_blockchain.hash_utils import calc_body_hash, calc_legacy_tran_hash
from useful_blockchain.signature import SignatureManager
from useful_blockchain.types import (
    Block,
    ChainVerificationResult,
    DEFAULT_GENESIS_PREV_HASH,
    TransactionBody,
)


class BlockChain:
    """
    ブロックチェーンクラス

    ブロックを連結してチェーン状に管理するクラスです。
    各ブロックには取引データ、タイムスタンプ、前のブロックへの参照が含まれます。
    """

    def __init__(
        self,
        enable_signature: bool = False,
        consensus: ConsensusProtocol | None = None,
        genesis_prev_hash: str = DEFAULT_GENESIS_PREV_HASH,
    ) -> None:
        self.chain: list[Block] = []
        self.enable_signature = enable_signature
        self.consensus = consensus
        self.genesis_prev_hash = genesis_prev_hash
        self.signature_manager = SignatureManager() if enable_signature else None

    def add_new_block(self, input_data: Any, output_data: Any) -> Block:
        new_transaction = self.__create_new_transaction(input_data, output_data)

        if len(self.chain) > 0:
            prev_hash = self.chain[-1]["block_header"]["tran_hash"]
        else:
            prev_hash = self.genesis_prev_hash

        body_hash = calc_body_hash(new_transaction)
        header: dict[str, Any] = {"prev_hash": prev_hash}

        if self.consensus is not None:
            header["consensus_type"] = self.consensus.consensus_type
            header["tran_hash"] = ""
        else:
            header["tran_hash"] = calc_legacy_tran_hash(prev_hash, body_hash)

        new_block: Block = {
            "block_index": len(self.chain) + 1,
            "block_item": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "block_header": header,  # type: ignore[typeddict-item]
            "tran_counter": len(input_data) + len(output_data),
            "tran_body": new_transaction,
        }

        if self.consensus is not None:
            new_block = self.consensus.prepare_block(new_block, self.chain)
        elif self.enable_signature and self.signature_manager:
            if self.signature_manager.private_key is None:
                raise ValueError(
                    "秘密鍵が設定されていません。generate_key_pair()を先に実行してください。"
                )
            new_block = self.signature_manager.sign_block(new_block)  # type: ignore[assignment]

        self.chain.append(new_block)
        if self.consensus is not None:
            self.consensus.on_block_added(new_block)
        return new_block

    def add_block(self, block: Block, validate: bool = True) -> bool:
        """外部から受信したブロックを追加する。"""
        if validate:
            previous = self.chain[-1] if self.chain else None
            if self.consensus is not None:
                link = self.consensus.validate_chain_link(
                    block, previous, self.genesis_prev_hash
                )
                if not link.valid:
                    return False
            elif previous is not None:
                if block["block_header"]["prev_hash"] != previous["block_header"]["tran_hash"]:
                    return False
            if self.consensus is not None:
                result = self.consensus.validate_block(block, self.chain)
                if not result.valid:
                    return False
            verification = verify_chain_integrity(
                self.chain + [block], self.consensus, self.genesis_prev_hash
            )
            if not verification.valid:
                return False

        self.chain.append(block)
        if self.consensus is not None:
            self.consensus.on_block_added(block)
        return True

    def replace_chain(
        self,
        new_chain: list[Block],
        *,
        genesis_stakes: dict[str, int] | None = None,
    ) -> bool:
        verification = verify_chain_integrity(
            new_chain, self.consensus, self.genesis_prev_hash
        )
        if not verification.valid:
            return False
        self.chain = list(new_chain)
        if self.consensus is not None and genesis_stakes is not None:
            from useful_blockchain.consensus.pos import ProofOfStake

            if isinstance(self.consensus, ProofOfStake):
                self.consensus.sync_validators_from_chain(self.chain, genesis_stakes)
        return True

    def verify_chain(self) -> ChainVerificationResult:
        return verify_chain_integrity(
            self.chain, self.consensus, self.genesis_prev_hash
        )

    def get_blocks_from(self, from_height: int) -> list[Block]:
        if from_height < 1:
            return list(self.chain)
        return self.chain[from_height - 1 :]

    def __create_new_transaction(self, input_data: Any, output_data: Any) -> TransactionBody:
        return {
            "input_data": input_data,
            "output_data": output_data,
        }

    def __calc_tran_hash(self, new_transaction: dict[str, Any]) -> str:
        tran_string = json.dumps(new_transaction, sort_keys=True).encode()
        return self.__hash(tran_string)

    def __hash(self, str_seed: Any) -> str:
        return hashlib.sha256(str(str_seed).encode()).hexdigest()

    def dump(self, block_index: int = 0) -> None:
        if block_index == 0:
            print(json.dumps(self.chain, indent=2))
        elif block_index < 1 or block_index > len(self.chain):
            print("無効なブロックインデックスです。")
        else:
            print(json.dumps(self.chain[block_index - 1], indent=2))

    def generate_key_pair(self) -> tuple[RSAPrivateKey, RSAPublicKey] | None:
        if not self.enable_signature or not self.signature_manager:
            print("署名機能が有効ではありません。")
            return None
        return self.signature_manager.generate_key_pair()

    def verify_block_signature(self, block_index: int) -> bool:
        if not self.enable_signature or not self.signature_manager:
            print("署名機能が有効ではありません。")
            return False
        if block_index < 1 or block_index > len(self.chain):
            print("無効なブロックインデックスです。")
            return False
        block = self.chain[block_index - 1]
        if "signature" not in block:
            print("このブロックには署名がありません。")
            return False
        return self.signature_manager.verify_block_signature(block)

    def verify_all_signatures(self) -> dict[str, bool | None]:
        if not self.enable_signature or not self.signature_manager:
            print("署名機能が有効ではありません。")
            return {}
        results: dict[str, bool | None] = {}
        for i, block in enumerate(self.chain, 1):
            if "signature" in block:
                results[f"block_{i}"] = self.signature_manager.verify_block_signature(block)
            else:
                results[f"block_{i}"] = None
        return results

    def export_public_key(self) -> bytes | None:
        if not self.enable_signature or not self.signature_manager:
            print("署名機能が有効ではありません。")
            return None
        return self.signature_manager.export_public_key()


if __name__ == "__main__":
    bc = BlockChain()
    bc.add_new_block("test", "test1")
    bc.add_new_block("test3", "test4")
    print(bc.chain)
