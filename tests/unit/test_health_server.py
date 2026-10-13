import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from useful_blockchain.observability.health_server import HealthServer
from useful_blockchain.observability.metrics import MetricsCollector
from useful_blockchain.types import ObservabilitySettings


async def _http_get(
    host: str,
    port: int,
    path: str,
    authorization: str | None = None,
) -> tuple[int, bytes]:
    reader, writer = await asyncio.open_connection(host, port)
    request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
    if authorization is not None:
        request += f"Authorization: {authorization}\r\n"
    request += "Connection: close\r\n\r\n"
    writer.write(request.encode())
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


@pytest.mark.asyncio
async def test_health_server_metrics_auth_valid_token():
    # Given: auth_enabled で正しい Bearer トークンを持つヘルスサーバー
    # When: /metrics にアクセスする
    # Then: 200 が返る
    token = "test-secret-token"

    async def readiness_checker() -> bool:
        return True

    settings = ObservabilitySettings(
        enabled=True,
        host="127.0.0.1",
        port=0,
        auth_enabled=True,
        auth_token=token,
    )
    metrics = MetricsCollector(settings)
    metrics.set_chain_height(1)
    server = HealthServer(settings, readiness_checker, metrics)
    await server.start()
    assert server.actual_port is not None

    try:
        status, body = await _http_get(
            "127.0.0.1",
            server.actual_port,
            "/metrics",
            authorization=f"Bearer {token}",
        )
        assert status == 200
        assert b"ebc_chain_height" in body
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_metrics_auth_missing_token():
    # Given: auth_enabled でトークンなしのリクエスト
    # When: /metrics にアクセスする
    # Then: 401 が返る
    async def readiness_checker() -> bool:
        return True

    settings = ObservabilitySettings(
        enabled=True,
        host="127.0.0.1",
        port=0,
        auth_enabled=True,
        auth_token="test-secret-token",
    )
    metrics = MetricsCollector(settings)
    metrics.set_chain_height(1)
    server = HealthServer(settings, readiness_checker, metrics)
    await server.start()
    assert server.actual_port is not None

    try:
        status, _ = await _http_get("127.0.0.1", server.actual_port, "/metrics")
        assert status == 401
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_metrics_auth_invalid_token():
    # Given: auth_enabled で不正な Bearer トークン
    # When: /metrics にアクセスする
    # Then: 401 が返る
    async def readiness_checker() -> bool:
        return True

    settings = ObservabilitySettings(
        enabled=True,
        host="127.0.0.1",
        port=0,
        auth_enabled=True,
        auth_token="test-secret-token",
    )
    metrics = MetricsCollector(settings)
    metrics.set_chain_height(1)
    server = HealthServer(settings, readiness_checker, metrics)
    await server.start()
    assert server.actual_port is not None

    try:
        status, _ = await _http_get(
            "127.0.0.1",
            server.actual_port,
            "/metrics",
            authorization="Bearer wrong-token",
        )
        assert status == 401
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_healthz_no_auth_when_auth_enabled():
    # Given: auth_enabled が true のヘルスサーバー
    # When: /healthz に認証なしでアクセスする
    # Then: 200 が返る
    async def readiness_checker() -> bool:
        return True

    settings = ObservabilitySettings(
        enabled=True,
        host="127.0.0.1",
        port=0,
        auth_enabled=True,
        auth_token="test-secret-token",
    )
    metrics = MetricsCollector(settings)
    server = HealthServer(settings, readiness_checker, metrics)
    await server.start()
    assert server.actual_port is not None

    try:
        status, body = await _http_get("127.0.0.1", server.actual_port, "/healthz")
        assert status == 200
        assert json.loads(body.decode()) == {"status": "ok"}
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_write_response_raises_timeout_when_client_not_reading():
    # Given: drain() が永久にブロックする writer（レスポンスを読まないクライアント）
    # When: _write_response を書き込みタイムアウト付きで呼ぶ
    # Then: asyncio.TimeoutError が送出され、送信バッファを破棄するため transport が abort される
    async def readiness_checker() -> bool:
        return True

    settings = ObservabilitySettings(enabled=True, host="127.0.0.1", port=0)
    server = HealthServer(settings, readiness_checker, MetricsCollector(settings))

    async def _drain_forever() -> None:
        await asyncio.sleep(3600)

    writer = MagicMock()
    writer.drain = _drain_forever

    with patch(
        "useful_blockchain.observability.health_server._WRITE_TIMEOUT_SECONDS",
        0.1,
    ):
        with pytest.raises(asyncio.TimeoutError):
            await server._write_response(writer, 200, "OK", "text/plain", b"body")

    writer.transport.abort.assert_called_once()


class _HangingCloseWriter:
    """close() 後も transport が abort されない限り wait_closed() が戻らない writer を模擬する。"""

    def __init__(self) -> None:
        self.transport = MagicMock()
        self.transport.abort = self.abort
        self.aborted = False
        self.closed = False
        self._closed_event = asyncio.Event()

    def write(self, data: bytes) -> None:
        pass

    async def drain(self) -> None:
        await asyncio.sleep(3600)

    def close(self) -> None:
        self.closed = True

    def abort(self) -> None:
        self.aborted = True
        self._closed_event.set()

    async def wait_closed(self) -> None:
        await self._closed_event.wait()


@pytest.mark.asyncio
async def test_handle_client_swallows_write_timeout():
    # Given: drain() がブロックし、close() 後も abort() されない限り wait_closed() が戻らない writer
    # When: レスポンスを読まないクライアントからの完全なリクエストで _handle_client を呼ぶ
    # Then: transport が abort されてハンドラは滞留せず完了し、close も呼ばれる
    async def readiness_checker() -> bool:
        return True

    settings = ObservabilitySettings(enabled=True, host="127.0.0.1", port=0)
    server = HealthServer(settings, readiness_checker, MetricsCollector(settings))

    reader = asyncio.StreamReader()
    reader.feed_data(b"GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n")
    reader.feed_eof()
    writer = _HangingCloseWriter()

    with patch(
        "useful_blockchain.observability.health_server._WRITE_TIMEOUT_SECONDS",
        0.1,
    ):
        await asyncio.wait_for(
            server._handle_client(reader, writer), timeout=5.0
        )
    assert writer.aborted
    assert writer.closed
