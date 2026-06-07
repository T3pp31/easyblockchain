"""ピア再接続のバックオフ管理。"""

from __future__ import annotations

import time

from useful_blockchain.types import ReconnectSettings


class ReconnectManager:
    """切断ピアへの指数バックオフ再接続を管理する。"""

    def __init__(self, settings: ReconnectSettings) -> None:
        self._settings = settings
        self._attempts: dict[str, int] = {}
        self._next_retry_at: dict[str, float] = {}

    def record_failure(self, url: str, now: float | None = None) -> None:
        """接続失敗を記録し、次回リトライ時刻を更新する。"""
        if not self._settings.enabled:
            return
        current = now if now is not None else time.monotonic()
        attempts = self._attempts.get(url, 0) + 1
        self._attempts[url] = attempts
        if self._settings.max_attempts > 0 and attempts >= self._settings.max_attempts:
            self._next_retry_at[url] = float("inf")
            return
        delay = min(
            self._settings.initial_delay_seconds
            * (self._settings.backoff_multiplier ** (attempts - 1)),
            self._settings.max_delay_seconds,
        )
        self._next_retry_at[url] = current + delay

    def record_success(self, url: str) -> None:
        """接続成功時にバックオフ状態をリセットする。"""
        self._attempts.pop(url, None)
        self._next_retry_at.pop(url, None)

    def should_retry(self, url: str, now: float | None = None) -> bool:
        """再接続を試行すべきか判定する。"""
        if not self._settings.enabled:
            return True
        current = now if now is not None else time.monotonic()
        next_at = self._next_retry_at.get(url)
        if next_at is None:
            return True
        if next_at == float("inf"):
            return False
        return current >= next_at

    def clear(self, url: str) -> None:
        """指定 URL の状態をクリアする。"""
        self._attempts.pop(url, None)
        self._next_retry_at.pop(url, None)
