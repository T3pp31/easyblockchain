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
        self._last_access: dict[str, float] = {}
        self._last_prune = 0.0

    def allow(self, key: str, now: float | None = None) -> bool:
        """イベントを許可するか判定し、許可時は記録する。"""
        current = now if now is not None else time.monotonic()
        self._prune_stale_keys(current)
        events = self._events[key]
        cutoff = current - self._window_seconds
        while events and events[0] < cutoff:
            events.popleft()
        self._last_access[key] = current
        if len(events) >= self._max_events:
            return False
        events.append(current)
        return True

    def _prune_stale_keys(self, current: float) -> None:
        """window_seconds 以上アクセスのないキーを削除する。"""
        if current - self._last_prune < self._window_seconds:
            return
        self._last_prune = current
        cutoff = current - self._window_seconds
        stale = [key for key, last in self._last_access.items() if last < cutoff]
        for key in stale:
            del self._events[key]
            del self._last_access[key]

    def reset(self, key: str) -> None:
        """指定キーの記録をクリアする。"""
        self._events.pop(key, None)
        self._last_access.pop(key, None)
