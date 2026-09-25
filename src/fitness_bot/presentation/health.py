from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        # Drain remaining headers so the client can finish sending.
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if line in (b"\r\n", b"\n", b""):
                break

        parts = request_line.decode("latin-1", errors="replace").split()
        method = parts[0] if parts else ""
        path = parts[1] if len(parts) > 1 else ""

        if method == "GET" and path == "/health":
            status = b"200 OK"
            body = b"ok"
        else:
            status = b"404 Not Found"
            body = b"not found"

        writer.write(
            b"HTTP/1.1 "
            + status
            + b"\r\nContent-Type: text/plain; charset=utf-8\r\n"
            + b"Content-Length: "
            + str(len(body)).encode("ascii")
            + b"\r\nConnection: close\r\n\r\n"
            + body,
        )
        await writer.drain()
    except (TimeoutError, ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


@asynccontextmanager
async def start_health_server(host: str, port: int) -> AsyncIterator[asyncio.Server]:
    server = await asyncio.start_server(_handle_client, host=host, port=port)
    try:
        yield server
    finally:
        server.close()
        await server.wait_closed()
