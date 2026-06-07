"""HTTP テスト用の軽量クライアントヘルパー。"""

from __future__ import annotations

import asyncio


async def http_get(
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
