"""GET_CHAIN limit クランプのユニットテスト。"""

from __future__ import annotations

import pytest

from useful_blockchain.network.node import _resolve_get_chain_batch_size


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
