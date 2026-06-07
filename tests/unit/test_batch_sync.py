from useful_blockchain.blockchain import BlockChain
from useful_blockchain.consensus.pow import ProofOfWork
from useful_blockchain.types import PowSettings


def _make_chain(length: int) -> BlockChain:
    consensus = ProofOfWork(PowSettings(initial_difficulty=1, max_mining_iterations=500000))
    chain = BlockChain(consensus=consensus)
    for i in range(length):
        chain.add_new_block([f"in-{i}"], [f"out-{i}"])
    return chain


def test_get_blocks_from_with_limit():
    # Given: 5ブロックのチェーン
    # When: from_height=2, limit=2 で取得する
    # Then: 2件のブロックが返る
    chain = _make_chain(5)
    blocks = chain.get_blocks_from(2, limit=2)
    assert len(blocks) == 2
    assert blocks[0]["block_index"] == 2
    assert blocks[1]["block_index"] == 3


def test_get_blocks_from_without_limit_returns_all_from_height():
    # Given: 5ブロックのチェーン
    # When: limit なしで from_height=3 を取得する
    # Then: 末尾まで3件返る
    chain = _make_chain(5)
    blocks = chain.get_blocks_from(3)
    assert len(blocks) == 3


def test_get_blocks_from_zero_height_returns_full_chain():
    # Given: 3ブロックのチェーン
    # When: from_height=0 で取得する
    # Then: 全ブロックが返る
    chain = _make_chain(3)
    blocks = chain.get_blocks_from(0, limit=10)
    assert len(blocks) == 3


def test_get_blocks_from_limit_exceeds_remaining():
    # Given: 2ブロックのチェーン
    # When: limit=100 で from_height=1 を取得する
    # Then: 2件のみ返る
    chain = _make_chain(2)
    blocks = chain.get_blocks_from(1, limit=100)
    assert len(blocks) == 2
