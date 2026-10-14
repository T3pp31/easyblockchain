import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from useful_blockchain.network.messages import MessageType, decode_message
from useful_blockchain.network.node import Node, _ChainSyncSession
from useful_blockchain.types import AppSettings


def _block(height):
    return {
        "block_index": height,
        "block_header": {"prev_hash": str(height - 1), "tran_hash": str(height)},
        "block_item": "2000-01-01 00:00:00", "tran_counter": 0,
        "tran_body": {"input_data": [], "output_data": []},
    }


def _response(blocks, start=1, has_more=False):
    return {"blocks": blocks, "from_height": start,
            "next_height": start + len(blocks), "has_more": has_more}


def _node():
    node = Node.__new__(Node)
    node.settings = AppSettings()
    node.settings.network.chain_sync_batch_size = 2
    node.blockchain = SimpleNamespace(chain=[])
    node.node_id = "test"
    node._pending_sync = {}
    node.p2p = SimpleNamespace(send_to_peer=AsyncMock(), peers={})
    node._close_peer = AsyncMock()
    node._resolve_fork = Mock()
    return node


@pytest.mark.asyncio
async def test_sync_accepts_contiguous_batches_and_resolves_once():
    # Given: 空チェーンからの同期セッション
    node = _node()
    started = asyncio.Event()
    node.p2p.send_to_peer.side_effect = lambda *args: started.set()
    task = asyncio.create_task(node._request_chain("peer"))
    await started.wait()
    # When: 連続する 2 バッチを受信する
    await node._handle_message("peer", MessageType.CHAIN_RESPONSE, _response([_block(1)], has_more=True))
    await node._handle_message("peer", MessageType.CHAIN_RESPONSE, _response([_block(2)], start=2))
    await task
    # Then: 次の高さを要求し、完全な候補を一度だけ検証する
    assert node.p2p.send_to_peer.await_args_list[-1].args[2]["from_height"] == 2
    node._resolve_fork.assert_called_once_with([_block(1), _block(2)])
    assert node._pending_sync == {}
    node._close_peer.assert_not_awaited()


@pytest.mark.parametrize("blocks", [[], [_block(1), _block(2)]])
def test_accepts_empty_final_or_exact_batch_and_total_limits(blocks):
    # Given: 件数・容量がちょうど上限のバッチ
    node = _node()
    node.settings.network.chain_sync_max_blocks = max(1, len(blocks))
    node.settings.network.chain_sync_max_bytes = len(json.dumps(blocks).encode())
    session = _ChainSyncSession()
    # When: 最終応答を検証する
    accepted = node._accept_chain_batch(session, _response(blocks))
    # Then: 空チェーンと上限ちょうどのデータを受け入れる
    assert accepted
    assert session.blocks == blocks


@pytest.mark.asyncio
@pytest.mark.parametrize("patch", [
    {"blocks": None}, {"blocks": {}}, {"blocks": "bad"}, {"blocks": [None]},
    {"from_height": 2}, {"from_height": None}, {"from_height": True},
    {"next_height": 1}, {"next_height": float("inf")}, {"next_height": "2"},
    {"has_more": "true"}, {"blocks": [], "next_height": 1, "has_more": True},
    {"blocks": [_block(2)]},
    {"blocks": [{"block_index": 1, "block_header": None}]},
    {"blocks": [{**_block(1), "block_index": True}]},
    {"blocks": [_block(1), _block(3)], "next_height": 3},
    {"blocks": [_block(1), {**_block(2), "block_header": {"prev_hash": "bad", "tran_hash": "2"}}], "next_height": 3},
    {"blocks": [_block(1), _block(2), _block(3)], "next_height": 4},
])
async def test_invalid_batch_aborts_without_fork_resolution(patch):
    # Given: 正常なセッションへの不正なピア応答
    node = _node()
    session = _ChainSyncSession()
    node._pending_sync["peer"] = session
    response = {**_response([_block(1)]), **copy.deepcopy(patch)}
    # When: ハンドラで検証する
    await node._handle_message("peer", MessageType.CHAIN_RESPONSE, response)
    # Then: 例外を出さず候補を破棄し、ピアを閉じる
    assert session.done.is_set()
    assert session.blocks == []
    node._close_peer.assert_awaited_once_with("peer")
    node._resolve_fork.assert_not_called()
    # When: 完了済みセッションにさらに応答が届く
    await node._handle_message("peer", MessageType.CHAIN_RESPONSE, _response([_block(1)]))
    # Then: 未要求の候補として採用しない
    node._resolve_fork.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["duplicate", "gap", "hash", "count", "bytes"])
async def test_later_invalid_batch_clears_previously_accumulated_data(failure):
    # Given: 最初の正常なバッチを受信したセッション
    node = _node()
    session = _ChainSyncSession()
    node._pending_sync["peer"] = session
    await node._handle_message("peer", MessageType.CHAIN_RESPONSE, _response([_block(1)], has_more=True))
    response = _response([_block(2)], start=2)
    # When: 続きに重複・欠落・ハッシュ不一致・上限超過がある
    if failure == "duplicate":
        response = _response([_block(1)])
    elif failure == "gap":
        response = _response([_block(3)], start=3)
    elif failure == "hash":
        response["blocks"][0]["block_header"]["prev_hash"] = "bad"
    elif failure == "count":
        node.settings.network.chain_sync_max_blocks = 1
    else:
        node.settings.network.chain_sync_max_bytes = session.received_bytes
    await node._handle_message("peer", MessageType.CHAIN_RESPONSE, response)
    # Then: 蓄積済みの断片も解決処理へ渡さない
    assert session.done.is_set() and session.blocks == []
    node._close_peer.assert_awaited_once()
    node._resolve_fork.assert_not_called()


@pytest.mark.asyncio
async def test_get_chain_handles_json_numeric_overflow():
    # Given: 有効な JSON の 1e999 が無限大にデコードされるメッセージ
    node = _node()
    node.blockchain.get_blocks_from = Mock(return_value=[])
    msg_type, payload = decode_message('{"type":"GET_CHAIN","from_height":1e999,"limit":1e999}')
    # When: 実際のメッセージハンドラで処理する
    await node._handle_message("peer", msg_type, payload)
    # Then: 上限付きの安全な要求へ戻し応答する
    node.blockchain.get_blocks_from.assert_called_once_with(1, limit=2)
    node.p2p.send_to_peer.assert_awaited_once()
