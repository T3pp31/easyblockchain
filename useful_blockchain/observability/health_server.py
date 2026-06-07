"""ヘルスチェックとメトリクス用の軽量 HTTP サーバー。"""

from __future__ import annotations

import asyncio
import json
import secrets
from typing import Awaitable, Callable

from useful_blockchain.observability.metrics import MetricsCollector
from useful_blockchain.types import ObservabilitySettings

ReadinessChecker = Callable[[], Awaitable[bool]]


class HealthServer:
    def __init__(
        self,
        settings: ObservabilitySettings,
        readiness_checker: ReadinessChecker,
        metrics: MetricsCollector,
        shutdown_timeout_seconds: float = 3.0,
    ) -> None:
        self._settings = settings
        self._readiness_checker = readiness_checker
        self._metrics = metrics
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._server: asyncio.Server | None = None
        self._actual_port: int | None = None

    @property
    def actual_port(self) -> int | None:
        return self._actual_port

    async def start(self) -> None:
        if not self._settings.enabled:
            return
        self._server = await asyncio.start_server(
            self._handle_client,
            host=self._settings.host,
            port=self._settings.port,
        )
        sockets = self._server.sockets
        if sockets:
            self._actual_port = sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await asyncio.wait_for(
                    self._server.wait_closed(),
                    timeout=self._shutdown_timeout_seconds,
                )
            except asyncio.TimeoutError:
                pass
            self._server = None
        self._actual_port = None

    def _requires_auth(self, path: str) -> bool:
        if not self._settings.auth_enabled:
            return False
        return path == self._settings.metrics_path

    def _is_authorized(self, headers: dict[str, str]) -> bool:
        expected = f"Bearer {self._settings.auth_token}"
        auth_header = headers.get("authorization", "")
        if len(auth_header) != len(expected):
            return False
        return secrets.compare_digest(auth_header, expected)

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not request_line:
                return
            parts = request_line.decode("utf-8", errors="replace").strip().split()
            if len(parts) < 2:
                return
            method, path = parts[0], parts[1]
            headers: dict[str, str] = {}
            while True:
                line = await reader.readline()
                if not line or line in (b"\r\n", b"\n"):
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if ":" in decoded:
                    key, _, value = decoded.partition(":")
                    headers[key.strip().lower()] = value.strip()

            if method != "GET":
                await self._write_response(writer, 405, "Method Not Allowed", "text/plain", b"")
                return

            if self._requires_auth(path) and not self._is_authorized(headers):
                await self._write_response(writer, 401, "Unauthorized", "text/plain", b"")
                return

            if path == self._settings.health_path:
                await self._write_response(
                    writer,
                    200,
                    "OK",
                    "application/json",
                    json.dumps({"status": "ok"}).encode("utf-8"),
                )
                return

            if path == self._settings.ready_path:
                ready = await self._readiness_checker()
                if ready:
                    body = json.dumps({"status": "ready"}).encode("utf-8")
                    await self._write_response(writer, 200, "OK", "application/json", body)
                else:
                    body = json.dumps({"status": "not_ready"}).encode("utf-8")
                    await self._write_response(
                        writer, 503, "Service Unavailable", "application/json", body
                    )
                return

            if path == self._settings.metrics_path:
                body = self._metrics.render()
                if not body:
                    await self._write_response(
                        writer, 503, "Service Unavailable", "text/plain", b"metrics disabled"
                    )
                    return
                content_type = "text/plain; version=0.0.4; charset=utf-8"
                await self._write_response(writer, 200, "OK", content_type, body)
                return

            await self._write_response(writer, 404, "Not Found", "text/plain", b"")
        except (asyncio.TimeoutError, ConnectionError):
            return
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except (OSError, ConnectionError, BrokenPipeError, ConnectionResetError):
                pass

    async def _write_response(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        reason: str,
        content_type: str,
        body: bytes,
    ) -> None:
        header = (
            f"HTTP/1.1 {status_code} {reason}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
        )
        writer.write(header.encode("utf-8") + body)
        await writer.drain()
