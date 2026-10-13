"""HTTP テスト用の軽量クライアントヘルパー。"""

from __future__ import annotations

import asyncio
import contextlib


async def http_get(
    host: str,
    port: int,
    path: str,
    authorization: str | None = None,
    timeout: float = 10.0,
) -> tuple[int, bytes]:
    async def _request() -> tuple[int, bytes]:
        reader, writer = await asyncio.open_connection(host, port)
        try:
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
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        if b"\r\n\r\n" in body:
            body = body.split(b"\r\n\r\n", 1)[1]
        return status_code, body

    return await asyncio.wait_for(_request(), timeout)
