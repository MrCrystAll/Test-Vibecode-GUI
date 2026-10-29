# SPDX-License-Identifier: Apache-2.0
"""Local security (TC-19): only the client that launched the backend may drive it.

One ASGI middleware, outermost, checks every HTTP request and WebSocket handshake in this order:

1. `Host` must name a loopback address (stops DNS rebinding) -> 400 `invalid_host`.
2. An `Origin` header, when present, must be allowed (browsers always send one; Electron's
   main process, the CLI and tests send none) -> 403 `origin_not_allowed`.
3. Every route except `/api/health` needs the per-launch token -> 401 `unauthorized`:
   HTTP: `Authorization: Bearer <token>`. WebSocket: the same header, or, because browsers
   cannot set headers on a WebSocket, the subprotocol `bearer.<token>` next to `studio.v1`
   (ADR-0006). The token is never accepted in a URL. CORS preflights (`OPTIONS` +
   `Access-Control-Request-Method`) carry no credentials by design and are passed to the CORS
   middleware unauthenticated.

Rejected WebSocket handshakes are closed before `accept`, which uvicorn turns into HTTP 403.
"""

import hmac
import json
import secrets
from collections.abc import Iterable
from dataclasses import dataclass, field

from starlette.types import ASGIApp, Receive, Scope, Send

from studio_backend.errors import error_body

PUBLIC_PATHS = frozenset({"/api/health"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
TOKEN_BYTES = 32  # 256 bits; the ticket asks for at least 128
BEARER_SUBPROTOCOL_PREFIX = "bearer."


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


@dataclass(frozen=True)
class SecurityConfig:
    token: str = field(default_factory=generate_token, repr=False)
    allowed_origins: tuple[str, ...] = ()
    allowed_hosts: frozenset[str] = LOOPBACK_HOSTS


def _host_name(host_header: str) -> str:
    """`127.0.0.1:8000` -> `127.0.0.1`, `[::1]:80` -> `::1`."""
    if host_header.startswith("["):
        return host_header[1:].split("]", 1)[0]
    return host_header.rsplit(":", 1)[0] if host_header.count(":") == 1 else host_header


def _headers(scope: Scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}


def _bearer(headers: dict[str, str]) -> str | None:
    scheme, _, credentials = headers.get("authorization", "").partition(" ")
    return credentials.strip() if scheme.lower() == "bearer" and credentials else None


def subprotocol_tokens(scope: Scope) -> Iterable[str]:
    """Tokens offered as `bearer.<token>` WebSocket subprotocols."""
    for protocol in scope.get("subprotocols", []):
        if protocol.startswith(BEARER_SUBPROTOCOL_PREFIX):
            yield protocol.removeprefix(BEARER_SUBPROTOCOL_PREFIX)


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, config: SecurityConfig) -> None:
        self.app = app
        self.config = config

    def _token_ok(self, candidate: str | None) -> bool:
        if candidate is None:
            return False
        return hmac.compare_digest(candidate.encode(), self.config.token.encode())

    def _check(self, scope: Scope) -> tuple[int, str, str] | None:
        """(status, code, message) for a rejected request, None if it may proceed."""
        headers = _headers(scope)
        if _host_name(headers.get("host", "")).lower() not in self.config.allowed_hosts:
            return 400, "invalid_host", "Host header is not a loopback address"
        origin = headers.get("origin")
        if origin is not None and origin not in self.config.allowed_origins:
            return 403, "origin_not_allowed", "Origin is not allowed"
        is_preflight = (
            scope["type"] == "http"
            and scope["method"] == "OPTIONS"
            and "access-control-request-method" in headers
        )
        if scope["path"] in PUBLIC_PATHS or is_preflight:
            return None
        candidates = [_bearer(headers)]
        if scope["type"] == "websocket":
            candidates.extend(subprotocol_tokens(scope))
        if not any(self._token_ok(c) for c in candidates):
            return 401, "unauthorized", "Missing or invalid bearer token"
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        rejection = self._check(scope)
        if rejection is None:
            await self.app(scope, receive, send)
        elif scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008, "reason": rejection[1]})
        else:
            await _send_error(send, *rejection)


async def _send_error(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps(error_body(code, message)).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if status == 401:
        headers.append((b"www-authenticate", b"Bearer"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
