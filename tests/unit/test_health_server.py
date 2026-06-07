import asyncio
import json

import pytest

from useful_blockchain.observability.health_server import HealthServer
from useful_blockchain.observability.metrics import MetricsCollector
from useful_blockchain.types import ObservabilitySettings


async def _http_get(host: str, port: int, path: str) -> tuple[int, bytes]:
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
    await writer.drain()
    status_line = await reader.readline()
    status_code = int(status_line.decode().split()[1])
    body = b""
    while True:
        chunk = await reader.read(4096)
        if not chunk:
            break
        body += chunk
    writer.close()
    await writer.wait_closed()
    if b"\r\n\r\n" in body:
        body = body.split(b"\r\n\r\n", 1)[1]
    return status_code, body


@pytest.mark.asyncio
async def test_health_server_healthz_and_readyz():
    # Given: readiness が true のヘルスサーバー
    # When: /healthz と /readyz にアクセスする
    # Then: 200 と期待 JSON が返る
    ready = True

    async def readiness_checker() -> bool:
        return ready

    settings = ObservabilitySettings(enabled=True, host="127.0.0.1", port=0)
    metrics = MetricsCollector(settings)
    server = HealthServer(settings, readiness_checker, metrics)
    await server.start()
    assert server.actual_port is not None

    try:
        status, body = await _http_get("127.0.0.1", server.actual_port, "/healthz")
        assert status == 200
        assert json.loads(body.decode()) == {"status": "ok"}

        status, body = await _http_get("127.0.0.1", server.actual_port, "/readyz")
        assert status == 200
        assert json.loads(body.decode()) == {"status": "ready"}
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_readyz_not_ready():
    # Given: readiness が false のヘルスサーバー
    # When: /readyz にアクセスする
    # Then: 503 が返る
    async def readiness_checker() -> bool:
        return False

    settings = ObservabilitySettings(enabled=True, host="127.0.0.1", port=0)
    metrics = MetricsCollector(settings)
    server = HealthServer(settings, readiness_checker, metrics)
    await server.start()
    assert server.actual_port is not None

    try:
        status, body = await _http_get("127.0.0.1", server.actual_port, "/readyz")
        assert status == 503
        assert json.loads(body.decode()) == {"status": "not_ready"}
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_metrics_and_not_found():
    # Given: メトリクス有効のヘルスサーバー
    # When: /metrics と未知パスにアクセスする
    # Then: 200/404 が返る
    settings = ObservabilitySettings(enabled=True, host="127.0.0.1", port=0)
    metrics = MetricsCollector(settings)
    metrics.set_chain_height(1)

    async def readiness_checker() -> bool:
        return True

    server = HealthServer(settings, readiness_checker, metrics)
    await server.start()
    assert server.actual_port is not None

    try:
        status, body = await _http_get("127.0.0.1", server.actual_port, "/metrics")
        if metrics.metrics_enabled:
            assert status == 200
            assert b"ebc_chain_height" in body
        else:
            assert status == 503

        status, _ = await _http_get("127.0.0.1", server.actual_port, "/unknown")
        assert status == 404
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_disabled():
    # Given: observability が無効
    # When: start を呼ぶ
    # Then: サーバーは起動しない
    async def readiness_checker() -> bool:
        return True

    settings = ObservabilitySettings(enabled=False)
    metrics = MetricsCollector(settings)
    server = HealthServer(settings, readiness_checker, metrics)
    await server.start()
    assert server.actual_port is None
    await server.stop()
