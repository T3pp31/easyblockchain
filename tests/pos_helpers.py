"""PoS テスト用ヘルパー。"""

from __future__ import annotations

from useful_blockchain.blockchain import BlockChain
from useful_blockchain.consensus.pos import ProofOfStake, validators_at_slot
from useful_blockchain.types import Block, PosSettings


def build_pos_chain(
    genesis_stakes: dict[str, int],
    instances: dict[str, ProofOfStake],
    settings: PosSettings,
    num_blocks: int,
) -> list[Block]:
    """各スロットの proposer が正しく署名した PoS チェーンを構築する。"""
    pos_ref = next(iter(instances.values()))
    chain: list[Block] = []
    for _ in range(num_blocks):
        slot = len(chain) + 1
        prefix_validators = validators_at_slot(chain, genesis_stakes, settings, slot)
        proposer = pos_ref.select_proposer(slot, prefix_validators)
        proposer_pos = instances[proposer]
        proposer_pos.sync_validators_from_chain(chain, genesis_stakes)
        bc = BlockChain(enable_signature=True, consensus=proposer_pos)
        bc.chain = list(chain)
        block = bc.add_new_block([f"in-{slot}"], [f"out-{slot}"])
        chain.append(block)
    return chain
