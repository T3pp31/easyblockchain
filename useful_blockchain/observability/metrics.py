"""Prometheus メトリクス（optional dependency）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from useful_blockchain.types import ObservabilitySettings


class _MetricsBackend(Protocol):
    def set_chain_height(self, height: int) -> None: ...

    def set_peer_count(self, count: int) -> None: ...

    def inc_blocks_accepted(self, amount: int = 1) -> None: ...

    def inc_sync_operations(self, amount: int = 1) -> None: ...

    def inc_pong_timeouts(self, amount: int = 1) -> None: ...

    def render(self) -> bytes: ...


class _NoOpMetrics:
    def set_chain_height(self, height: int) -> None:
        return None

    def set_peer_count(self, count: int) -> None:
        return None

    def inc_blocks_accepted(self, amount: int = 1) -> None:
        return None

    def inc_sync_operations(self, amount: int = 1) -> None:
        return None

    def inc_pong_timeouts(self, amount: int = 1) -> None:
        return None

    def render(self) -> bytes:
        return b""


class _PrometheusMetrics:
    def __init__(self) -> None:
        from prometheus_client import CollectorRegistry, Counter, Gauge

        self._registry = CollectorRegistry()
        self._chain_height = Gauge(
            "ebc_chain_height",
            "Current blockchain height",
            registry=self._registry,
        )
        self._peer_count = Gauge(
            "ebc_peer_count",
            "Number of connected peers",
            registry=self._registry,
        )
        self._blocks_accepted = Counter(
            "ebc_blocks_accepted_total",
            "Total number of accepted blocks",
            registry=self._registry,
        )
        self._sync_operations = Counter(
            "ebc_sync_operations_total",
            "Total number of chain sync operations",
            registry=self._registry,
        )
        self._pong_timeouts = Counter(
            "ebc_pong_timeouts_total",
            "Total number of PONG timeouts",
            registry=self._registry,
        )

    def set_chain_height(self, height: int) -> None:
        self._chain_height.set(height)

    def set_peer_count(self, count: int) -> None:
        self._peer_count.set(count)

    def inc_blocks_accepted(self, amount: int = 1) -> None:
        self._blocks_accepted.inc(amount)

    def inc_sync_operations(self, amount: int = 1) -> None:
        self._sync_operations.inc(amount)

    def inc_pong_timeouts(self, amount: int = 1) -> None:
        self._pong_timeouts.inc(amount)

    def render(self) -> bytes:
        from prometheus_client import generate_latest

        return generate_latest(self._registry)


def _create_backend() -> _MetricsBackend:
    try:
        import prometheus_client  # noqa: F401

        return _PrometheusMetrics()
    except ImportError:
        return _NoOpMetrics()


class MetricsCollector:
    """メトリクス更新のファサード。"""

    def __init__(self, settings: ObservabilitySettings) -> None:
        self._settings = settings
        if settings.enabled:
            backend = _create_backend()
            self._prometheus_available = isinstance(backend, _PrometheusMetrics)
            self._backend: _MetricsBackend = backend
        else:
            self._prometheus_available = False
            self._backend = _NoOpMetrics()

    @property
    def metrics_enabled(self) -> bool:
        return self._settings.enabled and self._prometheus_available

    def set_chain_height(self, height: int) -> None:
        self._backend.set_chain_height(height)

    def set_peer_count(self, count: int) -> None:
        self._backend.set_peer_count(count)

    def inc_blocks_accepted(self, amount: int = 1) -> None:
        self._backend.inc_blocks_accepted(amount)

    def inc_sync_operations(self, amount: int = 1) -> None:
        self._backend.inc_sync_operations(amount)

    def inc_pong_timeouts(self, amount: int = 1) -> None:
        self._backend.inc_pong_timeouts(amount)

    def render(self) -> bytes:
        return self._backend.render()
