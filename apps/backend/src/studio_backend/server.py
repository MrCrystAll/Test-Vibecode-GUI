# SPDX-License-Identifier: Apache-2.0
"""Run the app with uvicorn on a socket we bind ourselves, then announce the port on stdout.

Binding the socket here (instead of letting uvicorn do it) is what makes `--port 0` usable:
we know the real port before serving, and print it only once uvicorn has started.
"""

import asyncio
import json
import logging
import socket
import sys
from typing import TextIO

import uvicorn

from studio_backend.app import create_app
from studio_backend.settings import Settings

logger = logging.getLogger(__name__)


def bind_socket(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        raise
    return sock


def announce(event: dict[str, object], stream: TextIO | None = None) -> None:
    """Write one machine-readable event line to stdout (the only thing ever written there)."""
    out = sys.stdout if stream is None else stream
    out.write(json.dumps(event, separators=(",", ":")) + "\n")
    out.flush()


async def _serve(server: uvicorn.Server, sock: socket.socket) -> None:
    serve_task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        if serve_task.done():
            await serve_task  # re-raises the startup error, if any
            return
        await asyncio.sleep(0.01)
    host, port = sock.getsockname()[:2]
    logger.info("Listening on %s:%d", host, port)
    announce({"event": "listening", "port": port})
    await serve_task


def run(settings: Settings) -> None:
    sock = bind_socket(settings.host, settings.port)
    config = uvicorn.Config(
        create_app(),
        log_config=None,  # keep our JSON logging (logging_config.py)
        log_level=settings.log_level,
    )
    server = uvicorn.Server(config)
    try:
        asyncio.run(_serve(server, sock))
    finally:
        sock.close()
