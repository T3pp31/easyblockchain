"""IP およびピア単位のレート制限。"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """スライディングウィンドウによるイベント頻度制限。"""

    def __init__(self, max_events: int, window_seconds: float) -> None:
        self._max_events = max_events
        self._window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        """イベントを許可するか判定し、許可時は記録する。"""
        current = now if now is not None else time.monotonic()
        events = self._events[key]
        cutoff = current - self._window_seconds
        while events and events[0] < cutoff:
            events.popleft()
        if len(events) >= self._max_events:
            return False
        events.append(current)
        return True

    def reset(self, key: str) -> None:
        """指定キーの記録をクリアする。"""
        self._events.pop(key, None)
