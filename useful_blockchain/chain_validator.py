"""チェーン整合性検証。"""

from __future__ import annotations

from useful_blockchain.consensus.base import ConsensusProtocol
from useful_blockchain.hash_utils import calc_body_hash, calc_legacy_tran_hash
from useful_blockchain.types import Block, ChainVerificationResult, DEFAULT_GENESIS_PREV_HASH


def verify_chain_integrity(
    chain: list[Block],
    consensus: ConsensusProtocol | None = None,
    genesis_prev_hash: str = DEFAULT_GENESIS_PREV_HASH,
    *,
    genesis_stakes: dict[str, int] | None = None,
) -> ChainVerificationResult:
    from useful_blockchain.consensus.pos import ProofOfStake, validators_at_slot

    if isinstance(consensus, ProofOfStake) and genesis_stakes is not None:
        for index, block in enumerate(chain):
            previous = chain[index - 1] if index > 0 else None
            if previous is not None:
                link = consensus.validate_chain_link(block, previous, genesis_prev_hash)
                if not link.valid:
                    return ChainVerificationResult(
                        valid=False,
                        failed_at_index=index + 1,
                        reason=link.reason,
                    )
            else:
                if block["block_header"]["prev_hash"] != genesis_prev_hash:
                    return ChainVerificationResult(
                        valid=False,
                        failed_at_index=index + 1,
                        reason="genesis prev_hash mismatch",
                    )
                link = consensus.validate_chain_link(block, None, genesis_prev_hash)
                if not link.valid:
                    return ChainVerificationResult(
                        valid=False,
                        failed_at_index=index + 1,
                        reason=link.reason,
                    )

            slot = int(block.get("block_header", {}).get("slot", index + 1))
            prefix_validators = validators_at_slot(
                chain[:index], genesis_stakes, consensus.settings, slot
            )
            result = consensus.validate_block(
                block,
                chain[:index],
                validators_at_state=prefix_validators,
            )
            if not result.valid:
                return ChainVerificationResult(
                    valid=False,
                    failed_at_index=index + 1,
                    reason=result.reason,
                )
        return ChainVerificationResult(valid=True)

    for index, block in enumerate(chain):
        previous = chain[index - 1] if index > 0 else None
        if previous is not None:
            if consensus is not None:
                link = consensus.validate_chain_link(block, previous, genesis_prev_hash)
            else:
                prev_tran = previous["block_header"]["tran_hash"]
                if block["block_header"]["prev_hash"] != prev_tran:
                    return ChainVerificationResult(
                        valid=False,
                        failed_at_index=index + 1,
                        reason="prev_hash mismatch",
                    )
                if block["block_index"] != previous["block_index"] + 1:
                    return ChainVerificationResult(
                        valid=False,
                        failed_at_index=index + 1,
                        reason="block_index mismatch",
                    )
        else:
            if block["block_header"]["prev_hash"] != genesis_prev_hash:
                return ChainVerificationResult(
                    valid=False,
                    failed_at_index=index + 1,
                    reason="genesis prev_hash mismatch",
                )
            if consensus is not None:
                link = consensus.validate_chain_link(block, None, genesis_prev_hash)
                if not link.valid:
                    return ChainVerificationResult(
                        valid=False,
                        failed_at_index=index + 1,
                        reason=link.reason,
                    )

        header = block.get("block_header", {})
        consensus_type = header.get("consensus_type")
        if consensus is not None and consensus_type:
            result = consensus.validate_block(block, chain[:index])
            if not result.valid:
                return ChainVerificationResult(
                    valid=False,
                    failed_at_index=index + 1,
                    reason=result.reason,
                )
        elif consensus is None and not consensus_type:
            body_hash = calc_body_hash(block["tran_body"])
            expected = calc_legacy_tran_hash(header["prev_hash"], body_hash)
            if header.get("tran_hash") != expected:
                return ChainVerificationResult(
                    valid=False,
                    failed_at_index=index + 1,
                    reason="legacy tran_hash mismatch",
                )

    return ChainVerificationResult(valid=True)
