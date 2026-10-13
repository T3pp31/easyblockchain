import argparse
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from useful_blockchain.cli import _build_overrides, _build_parser, run


def _make_mock_node() -> AsyncMock:
    mock_node = AsyncMock()
    mock_node.node_id = "node-test"
    mock_node.p2p.local_url = "ws://127.0.0.1:8765"
    mock_node.settings.consensus.type = "pow"
    mock_node.settings.node.log_level = "INFO"
    mock_node.settings.observability.log_format = "text"
    return mock_node


def test_build_overrides_from_args():
    # Given: CLI 引数
    # When: _build_overrides を呼ぶ
    # Then: 設定上書き辞書が構築される
    args = argparse.Namespace(
        consensus="pow",
        port=8765,
        bootstrap=["ws://127.0.0.1:8765"],
        log_level="DEBUG",
    )
    overrides = _build_overrides(args)
    assert overrides["consensus"]["type"] == "pow"
    assert overrides["network"]["port"] == 8765
    assert overrides["network"]["bootstrap_peers"] == ["ws://127.0.0.1:8765"]
    assert overrides["node"]["log_level"] == "DEBUG"


def _patch_node(mock_node: AsyncMock, stop_event: object):
    return (
        patch("useful_blockchain.cli.Node", return_value=mock_node),
        patch("useful_blockchain.cli.asyncio.Event", return_value=stop_event),
    )


@pytest.mark.asyncio
async def test_run_starts_and_stops_node_on_signal():
    # Given: シグナル受信済みの停止イベント
    # When: run を実行する
    # Then: start/stop が呼ばれる
    mock_node = _make_mock_node()
    stop_event = asyncio.Event()
    stop_event.set()

    args = _build_parser().parse_args(["--consensus", "pow", "--port", "8765"])

    node_patch, event_patch = _patch_node(mock_node, stop_event)
    with node_patch, event_patch:
        result = await run(args)

    assert result == 0
    mock_node.start.assert_awaited_once()
    mock_node.stop.assert_awaited_once()


class _CancelledWaitEvent:
    def set(self) -> None:
        pass

    def wait(self) -> None:
        raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_run_stops_node_on_cancellation():
    # Given: wait() が CancelledError を投げる停止イベント（asyncio.run の SIGINT 処理を模擬）
    # When: run を実行する
    # Then: stop が呼ばれて正常終了する
    mock_node = _make_mock_node()
    stop_event = _CancelledWaitEvent()

    args = _build_parser().parse_args(["--consensus", "pow", "--port", "8765"])

    node_patch, event_patch = _patch_node(mock_node, stop_event)
    with node_patch, event_patch:
        result = await run(args)

    assert result == 0
    mock_node.start.assert_awaited_once()
    mock_node.stop.assert_awaited_once()
