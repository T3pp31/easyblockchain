import pytest

from useful_blockchain.blockchain import BlockChain
from useful_blockchain.consensus.pow import ProofOfWork
from useful_blockchain.types import PowSettings


@pytest.mark.integration
def test_pow_blockchain_verify_chain():
    pow_algo = ProofOfWork(PowSettings(initial_difficulty=1, max_mining_iterations=200000))
    bc = BlockChain(consensus=pow_algo)
    bc.add_new_block(["a"], ["b"])
    bc.add_new_block(["c"], ["d"])
    result = bc.verify_chain()
    assert result.valid is True
    assert len(bc.chain) == 2
    assert bc.chain[1]["block_header"]["prev_hash"] == bc.chain[0]["block_header"]["tran_hash"]
