from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

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
async def test_health_server_slowloris_header_timeout():
    # Given: リクエスト行のみ送りヘッダを送らない接続
    # When: ヘッダ読み込みデッドラインを短くして待機する
    # Then: タイムアウトでサーバーが接続を切断する
    async def readiness_checker() -> bool:
        return True

    settings = ObservabilitySettings(enabled=True, host="127.0.0.1", port=0)
    metrics = MetricsCollector(settings)
    server = HealthServer(settings, readiness_checker, metrics)
    await server.start()
    assert server.actual_port is not None

    try:
        with patch(
            "useful_blockchain.observability.health_server._HEADER_DEADLINE_SECONDS",
            0.1,
        ):
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", server.actual_port
            )
            writer.write(b"GET /healthz HTTP/1.1\r\n")
            await writer.drain()
            data = await asyncio.wait_for(reader.read(1024), timeout=5.0)
            assert data == b""
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_header_line_limit():
    # Given: 上限を超える数のヘッダ行を送る接続
    # When: ヘッダを送り続ける
    # Then: 上限到達でサーバーが接続を切断する
    async def readiness_checker() -> bool:
        return True

    settings = ObservabilitySettings(enabled=True, host="127.0.0.1", port=0)
    metrics = MetricsCollector(settings)
    server = HealthServer(settings, readiness_checker, metrics)
    await server.start()
    assert server.actual_port is not None

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.actual_port)
        writer.write(b"GET /healthz HTTP/1.1\r\n")
        for _ in range(150):
            writer.write(b"X-Pad: a\r\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(1024), timeout=5.0)
        assert data == b""
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_header_byte_limit():
    # Given: ヘッダ合計バイト上限を小さくした設定
    # When: 上限を超える長いヘッダ行を 1 行送る
    # Then: 読み込み後に合計バイトが判定され、サーバーが接続を切断する
    async def readiness_checker() -> bool:
        return True

    settings = ObservabilitySettings(enabled=True, host="127.0.0.1", port=0)
    metrics = MetricsCollector(settings)
    server = HealthServer(settings, readiness_checker, metrics)
    await server.start()
    assert server.actual_port is not None

    try:
        with patch(
            "useful_blockchain.observability.health_server._MAX_HEADER_BYTES",
            10,
        ):
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", server.actual_port
            )
            writer.write(b"GET /healthz HTTP/1.1\r\n")
            writer.write(b"X-Pad: aaaaaaaaaaaaaaaaaaaa\r\n")
            await writer.drain()
            data = await asyncio.wait_for(reader.read(1024), timeout=5.0)
            assert data == b""
    finally:
        await server.stop()
