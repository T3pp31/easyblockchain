import argparse
import asyncio
import signal
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


def _patch_node(mock_node: AsyncMock):
    return patch("useful_blockchain.cli.Node", return_value=mock_node)


@pytest.mark.asyncio
async def test_run_starts_and_stops_node_on_signal():
    # Given: シグナル受信済みの停止イベント（SIGINT/SIGTERM を模擬）
    # When: run を実行する
    # Then: start/stop が呼ばれる
    mock_node = _make_mock_node()
    stop_event = asyncio.Event()
    stop_event.set()

    args = _build_parser().parse_args(["--consensus", "pow", "--port", "8765"])

    with _patch_node(mock_node):
        result = await run(args, stop_event=stop_event)

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

    with _patch_node(mock_node):
        result = await run(args, stop_event=stop_event)

    assert result == 0
    mock_node.start.assert_awaited_once()
    mock_node.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_registers_signal_handlers_before_start():
    # Given: add_signal_handler をスパイしたイベントループ
    # When: run を実行する
    # Then: node.start() より前に SIGINT/SIGTERM への停止イベント設定が登録される
    mock_node = _make_mock_node()
    stop_event = asyncio.Event()
    stop_event.set()

    args = _build_parser().parse_args(["--consensus", "pow", "--port", "8765"])

    call_order: list[str] = []

    async def _record_start():
        call_order.append("start")

    def _record_register(sig, callback):
        call_order.append("register")

    mock_node.start.side_effect = _record_start

    loop = asyncio.get_running_loop()
    with _patch_node(mock_node), patch.object(
        loop, "add_signal_handler", side_effect=_record_register
    ) as mock_add:
        result = await run(args, stop_event=stop_event)

    assert mock_add.call_count == 2
    registered_sigs = [call.args[0] for call in mock_add.call_args_list]
    assert registered_sigs == [signal.SIGINT, signal.SIGTERM]
    assert all(call.args[1] == stop_event.set for call in mock_add.call_args_list)
    assert call_order == ["register", "register", "start"]
    assert result == 0
    mock_node.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_stops_node_when_signal_handler_unavailable():
    # Given: add_signal_handler が NotImplementedError を投げる環境（Windows 等を模擬）
    # When: run を実行する
    # Then: 例外を握りつぶし、start/stop が呼ばれて正常終了する
    mock_node = _make_mock_node()
    stop_event = asyncio.Event()
    stop_event.set()

    args = _build_parser().parse_args(["--consensus", "pow", "--port", "8765"])

    loop = asyncio.get_running_loop()
    with _patch_node(mock_node), patch.object(
        loop, "add_signal_handler", side_effect=NotImplementedError
    ):
        result = await run(args, stop_event=stop_event)

    assert result == 0
    mock_node.start.assert_awaited_once()
    mock_node.stop.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["start", "add_block"])
async def test_run_stops_node_on_operation_failure(operation):
    # Given: 起動または起動後のブロック追加に失敗するノード
    node = _make_mock_node()
    getattr(node, operation).side_effect = OSError("disk failure")
    args = _build_parser().parse_args(["--add-block", "in", "out"])
    # When: CLI を実行する
    with _patch_node(node), pytest.raises(OSError, match="disk failure"):
        await run(args, stop_event=asyncio.Event())
    # Then: 元の例外を伝播しつつ必ず停止する
    node.stop.assert_awaited_once()
