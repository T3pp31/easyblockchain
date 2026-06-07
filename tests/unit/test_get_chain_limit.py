"""GET_CHAIN limit クランプのユニットテスト。"""

from __future__ import annotations

import pytest

from useful_blockchain.network.node import (
    _resolve_get_chain_batch_size,
    _resolve_get_chain_from_height,
)


@pytest.mark.parametrize(
    ("limit_raw", "max_batch", "expected"),
    [
        (None, 100, 100),
        (50, 100, 50),
        (100, 100, 100),
        (999999, 100, 100),
        (0, 100, 1),
        (-5, 100, 1),
        ("abc", 100, 100),
        (3.7, 100, 3),
    ],
)
def test_resolve_get_chain_batch_size(
    limit_raw: object, max_batch: int, expected: int
) -> None:
    # Given: limit 値と上限
    # When: _resolve_get_chain_batch_size を呼ぶ
    # Then: クランプ後の batch size が返る
    assert _resolve_get_chain_batch_size(limit_raw, max_batch) == expected


@pytest.mark.parametrize(
    ("from_height_raw", "expected"),
    [
        (None, 1),
        (1, 1),
        (5, 5),
        (0, 1),
        (-1, 1),
        ("abc", 1),
        (3.7, 3),
    ],
)
def test_resolve_get_chain_from_height(
    from_height_raw: object, expected: int
) -> None:
    # Given: from_height 値
    # When: _resolve_get_chain_from_height を呼ぶ
    # Then: クランプ後の from_height が返る
    assert _resolve_get_chain_from_height(from_height_raw) == expected
