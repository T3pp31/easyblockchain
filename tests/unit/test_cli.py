import argparse
from unittest.mock import AsyncMock, patch

import pytest

from useful_blockchain.cli import _build_overrides, _build_parser, run


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


@pytest.mark.asyncio
async def test_run_starts_and_stops_node():
    # Given: モック Node
    # When: run を KeyboardInterrupt で終了する
    # Then: start/stop が呼ばれる
    mock_node = AsyncMock()
    mock_node.node_id = "node-test"
    mock_node.p2p.local_url = "ws://127.0.0.1:8765"
    mock_node.settings.consensus.type = "pow"

    args = _build_parser().parse_args(["--consensus", "pow", "--port", "8765"])

    with (
        patch("useful_blockchain.cli.Node", return_value=mock_node),
        patch("useful_blockchain.cli.asyncio.sleep", side_effect=KeyboardInterrupt),
    ):
        result = await run(args)

    assert result == 0
    mock_node.start.assert_awaited_once()
    mock_node.stop.assert_awaited_once()
