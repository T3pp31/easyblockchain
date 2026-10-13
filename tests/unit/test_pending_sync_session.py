import asyncio
from types import SimpleNamespace

import pytest

from useful_blockchain.network.node import Node
from useful_blockchain.types import Block


def _make_node(timeout: float = 5.0) -> Node:
    node = Node.__new__(Node)
    node._pending_sync = {}
    node._send_calls: list[str] = []
    node._resolve_calls: list[list[Block]] = []
    node.blockchain = SimpleNamespace(chain=[])

    async def _send_chain_request(peer_id: str, _from_height: int) -> None:
        node._send_calls.append(peer_id)

    def _resolve_fork(remote_chain: list[Block]) -> None:
        node._resolve_calls.append(remote_chain)

    node._send_chain_request = _send_chain_request  # type: ignore[method-assign]
    node._resolve_fork = _resolve_fork  # type: ignore[method-assign]
    node.settings = SimpleNamespace(
        network=SimpleNamespace(chain_sync_timeout_seconds=timeout)
    )
    return node


def _block(index: int) -> Block:
    return {
        "block_index": index,
        "block_item": "2000-01-01 00:00:00",
        "block_header": {"prev_hash": "0" * 64, "tran_hash": str(index) * 64},
        "tran_counter": 1,
        "tran_body": {"input_data": [], "output_data": []},
    }


@pytest.mark.asyncio
async def test_concurrent_request_chain_does_not_overwrite_session() -> None:
    # Given: 進行中の同期セッションが存在するピア
    # When: 同一ピアに対して _request_chain を重複実行する
    # Then: 既存セッションは上書きされず、リクエストは 1 回のみ送信される
    node = _make_node()
    task = asyncio.create_task(node._request_chain("peer-a"))
    await asyncio.sleep(0.01)
    existing = node._pending_sync.get("peer-a")
    assert existing is not None

    await node._request_chain("peer-a")

    assert node._pending_sync.get("peer-a") is existing
    assert node._send_calls == ["peer-a"]

    existing.blocks.append(_block(2))
    existing.done.set()
    await task

    assert "peer-a" not in node._pending_sync
    assert node._resolve_calls == [[_block(2)]]


@pytest.mark.asyncio
async def test_new_session_after_timeout_is_preserved() -> None:
    # Given: 同期セッションがタイムアウトした直後に新セッションが開始された状態
    # When: 新セッションへ応答が到着する
    # Then: 新セッションの応答が正しく処理され、セッションは除去される
    node = _make_node(timeout=0.05)
    await node._request_chain("peer-a")
    assert "peer-a" not in node._pending_sync

    task = asyncio.create_task(node._request_chain("peer-a"))
    await asyncio.sleep(0.01)
    session = node._pending_sync.get("peer-a")
    assert session is not None

    session.blocks.append(_block(1))
    session.done.set()
    await task

    assert "peer-a" not in node._pending_sync
    assert node._resolve_calls == [[_block(1)]]
