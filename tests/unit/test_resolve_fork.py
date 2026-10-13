import copy

from useful_blockchain.blockchain import BlockChain
from useful_blockchain.consensus.pow import ProofOfWork
from useful_blockchain.network.node import Node
from useful_blockchain.types import Block, PowSettings


def _make_chain(length: int) -> BlockChain:
    consensus = ProofOfWork(PowSettings(initial_difficulty=1, max_mining_iterations=500000))
    chain = BlockChain(consensus=consensus)
    for i in range(length):
        chain.add_new_block([f"in-{i}"], [f"out-{i}"])
    return chain


def _make_node(chain: BlockChain) -> Node:
    node = Node.__new__(Node)
    node.blockchain = chain
    node.consensus = chain.consensus
    node.genesis_stakes = None
    node._persist_state = lambda: None  # type: ignore[method-assign]
    return node


def _make_suffix(local: BlockChain, extra: int) -> list[Block]:
    longer = copy.deepcopy(local.chain)
    extended = BlockChain(consensus=local.consensus)
    extended.chain = longer
    for i in range(extra):
        extended.add_new_block([f"extra-in-{i}"], [f"extra-out-{i}"])
    return longer[len(local.chain):]


def test_resolve_fork_extends_local_chain_with_suffix() -> None:
    # Given: 2ブロックのローカルチェーンと、それに接続する末尾断片
    # When: _resolve_fork に断片を渡す
    # Then: ローカルチェーンが断片で延長される
    local = _make_chain(2)
    node = _make_node(local)
    suffix = _make_suffix(local, 1)
    original_prefix = list(local.chain)

    node._resolve_fork(suffix)

    assert len(node.blockchain.chain) == 3
    assert node.blockchain.chain[:2] == original_prefix


def test_resolve_fork_discards_fragment_not_extending_local_chain() -> None:
    # Given: ローカルチェーン末尾と接続しない断片
    # When: _resolve_fork に断片を渡す
    # Then: チェーンは変更されない
    local = _make_chain(2)
    node = _make_node(local)
    fragment: list[Block] = [
        {
            "block_index": 3,
            "block_item": "2000-01-01 00:00:00",
            "block_header": {"prev_hash": "deadbeef", "tran_hash": "0" * 64},
            "tran_counter": 1,
            "tran_body": {"input_data": [], "output_data": []},
        }
    ]

    node._resolve_fork(fragment)

    assert len(node.blockchain.chain) == 2
    assert node.blockchain.chain == local.chain


def test_resolve_fork_accepts_full_chain_on_empty_local() -> None:
    # Given: 空のローカルチェーンと完全チェーン候補
    # When: _resolve_fork に完全チェーンを渡す
    # Then: チェーンが置換される
    empty = _make_chain(0)
    node = _make_node(empty)
    full_chain = _make_chain(2).chain

    node._resolve_fork(full_chain)

    assert len(node.blockchain.chain) == 2
    assert node.blockchain.chain == full_chain


def test_resolve_fork_replaces_local_with_longer_full_chain() -> None:
    # Given: 非空のローカルチェーンと、ジェネシス起点のより長い完全チェーン
    # When: _resolve_fork に完全チェーンを渡す
    # Then: ローカルチェーンが正規チェーンで置換される
    local = _make_chain(2)
    node = _make_node(local)
    full_chain = _make_chain(3).chain

    node._resolve_fork(full_chain)

    assert node.blockchain.chain == full_chain
