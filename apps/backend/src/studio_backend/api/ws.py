# SPDX-License-Identifier: Apache-2.0
"""The single WebSocket endpoint `/ws` (TC-20).

Authentication, Host and Origin checks happen before this code runs (security.py). Here:
- the client must offer the `studio.v1` subprotocol, which is echoed back;
- the server sends `ping` every `app.state.ws_ping_interval` seconds;
- each client message is validated; a bad one gets an `error` event and the connection stays open.
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from studio_backend.events import (
    CLIENT_TYPES,
    ENVELOPE_KEYS,
    PROTOCOL_VERSION,
    SUBPROTOCOL,
    TOPICS,
    ErrorCode,
    ErrorPayload,
    ReplyPayload,
    TopicReplyPayload,
    WsError,
    WsPing,
    WsPong,
    WsServerMessage,
    WsSubscribe,
    WsSubscribed,
    WsUnsubscribe,
    WsUnsubscribed,
    client_message_adapter,
    server_message_adapter,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Close code for a policy violation (RFC 6455), as used by the security middleware.
CLOSE_POLICY_VIOLATION = 1008


class _RejectedError(Exception):
    def __init__(self, code: ErrorCode, message: str, reply_to: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.reply_to = reply_to


class Session:
    """One connected client: its subscriptions and the messages it sent."""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.topics: set[str] = set()
        self._send_lock = asyncio.Lock()

    async def send(self, message: WsServerMessage) -> None:
        text = server_message_adapter.dump_json(message).decode()
        async with self._send_lock:
            await self.websocket.send_text(text)

    async def ping_forever(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            await self.send(WsPing())

    async def handle(self, text: str) -> None:
        try:
            await self._dispatch(_parse(text))
        except _RejectedError as rejected:
            await self.send(
                WsError(
                    payload=ErrorPayload(
                        code=rejected.code, message=rejected.message, reply_to=rejected.reply_to
                    )
                )
            )

    async def _dispatch(self, message: Any) -> None:
        if isinstance(message, WsPing):
            await self.send(WsPong(payload=ReplyPayload(reply_to=message.id)))
        elif isinstance(message, WsSubscribe):
            self.topics.add(message.payload.topic)
            payload = TopicReplyPayload(topic=message.payload.topic, reply_to=message.id)
            await self.send(WsSubscribed(payload=payload))
        elif isinstance(message, WsUnsubscribe):
            self.topics.discard(message.payload.topic)
            payload = TopicReplyPayload(topic=message.payload.topic, reply_to=message.id)
            await self.send(WsUnsubscribed(payload=payload))
        # A client pong only proves liveness; nothing to answer.


def _parse(text: str) -> Any:
    """Validate one client message, or raise _RejectedError with the most specific error code."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        raise _RejectedError("invalid_json", "Message is not valid JSON") from None
    if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
        raise _RejectedError("invalid_envelope", "Message must be an object with a string `type`")
    reply_to = raw["id"] if isinstance(raw.get("id"), str) else None
    missing = sorted(ENVELOPE_KEYS - raw.keys())
    if missing:
        raise _RejectedError(
            "invalid_envelope", f"Missing envelope keys: {', '.join(missing)}", reply_to
        )
    if raw.get("version") != PROTOCOL_VERSION:
        raise _RejectedError(
            "unsupported_version", f"Protocol version must be {PROTOCOL_VERSION}", reply_to
        )
    if raw["type"] not in CLIENT_TYPES:
        raise _RejectedError("unknown_type", f"Unknown message type {raw['type']!r}", reply_to)
    payload = raw.get("payload")
    if raw["type"] in ("subscribe", "unsubscribe") and isinstance(payload, dict):
        topic = payload.get("topic")
        if isinstance(topic, str) and topic not in TOPICS:
            raise _RejectedError("unknown_topic", f"Unknown topic {topic!r}", reply_to)
    try:
        return client_message_adapter.validate_python(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"][1:]) or "message"
        raise _RejectedError("invalid_payload", f"{where}: {first['msg']}", reply_to) from None


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    if SUBPROTOCOL not in websocket.scope.get("subprotocols", []):
        await websocket.close(code=CLOSE_POLICY_VIOLATION, reason=f"{SUBPROTOCOL} required")
        return
    await websocket.accept(subprotocol=SUBPROTOCOL)
    session = Session(websocket)
    pinger = asyncio.create_task(session.ping_forever(websocket.app.state.ws_ping_interval))
    try:
        while True:
            await session.handle(await websocket.receive_text())
    except WebSocketDisconnect:
        pass
    finally:
        pinger.cancel()
