# SPDX-License-Identifier: Apache-2.0
"""WebSocket message envelope and event types (TC-20, ADR-0006).

Every message, in both directions, is one JSON object:

    {"type": "<event>", "version": 1, "id": "<unique>", "ts": "<ISO-8601 UTC>", "payload": {...}}

`version` is the protocol version (`PROTOCOL_VERSION`), bumped on a breaking change. The models
are published in `packages/contract/openapi.json` (`components.schemas`), so the UI gets typed
unions (`WsClientMessage`, `WsServerMessage`) from the same generator as the HTTP client.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PROTOCOL_VERSION: Literal[1] = 1
SUBPROTOCOL = "studio.v1"

Topic = Literal["system"]
TOPICS: tuple[Topic, ...] = ("system",)

ErrorCode = Literal[
    "invalid_json",
    "invalid_envelope",
    "unsupported_version",
    "unknown_type",
    "invalid_payload",
    "unknown_topic",
]


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(UTC)


ENVELOPE_KEYS = frozenset({"type", "version", "id", "ts", "payload"})


class _Message(BaseModel):
    # Defaults only help the server build messages; on the wire every envelope key is required
    # (the published schema says so, and the backend rejects client messages missing one).
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

    version: Literal[1] = PROTOCOL_VERSION
    id: str = Field(default_factory=new_id, min_length=1, max_length=64)
    ts: datetime = Field(default_factory=now)


# --- payloads ------------------------------------------------------------------------------------


class EmptyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReplyPayload(BaseModel):
    """Payload of a reply: the `id` of the client message it answers, if any."""

    model_config = ConfigDict(extra="forbid")

    reply_to: str | None = None


class TopicPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: Topic


class TopicReplyPayload(TopicPayload):
    reply_to: str


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    reply_to: str | None = None


# --- messages ------------------------------------------------------------------------------------


class WsPing(_Message):
    """Keep-alive. The server sends one every ping interval; a client may send one too."""

    type: Literal["ping"] = "ping"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class WsPong(_Message):
    """Answer to a `ping`. The server's pong names the client ping in `payload.reply_to`."""

    type: Literal["pong"] = "pong"
    payload: ReplyPayload = Field(default_factory=ReplyPayload)


class WsSubscribe(_Message):
    """Client: start receiving events of a topic."""

    type: Literal["subscribe"] = "subscribe"
    payload: TopicPayload


class WsUnsubscribe(_Message):
    """Client: stop receiving events of a topic."""

    type: Literal["unsubscribe"] = "unsubscribe"
    payload: TopicPayload


class WsSubscribed(_Message):
    """Server: the subscription in `payload.reply_to` is active."""

    type: Literal["subscribed"] = "subscribed"
    payload: TopicReplyPayload


class WsUnsubscribed(_Message):
    """Server: the topic is no longer delivered."""

    type: Literal["unsubscribed"] = "unsubscribed"
    payload: TopicReplyPayload


class WsError(_Message):
    """Server: a client message was rejected. The connection stays open."""

    type: Literal["error"] = "error"
    payload: ErrorPayload


WsClientMessage = Annotated[
    WsPing | WsPong | WsSubscribe | WsUnsubscribe, Field(discriminator="type")
]
WsServerMessage = Annotated[
    WsPing | WsPong | WsSubscribed | WsUnsubscribed | WsError, Field(discriminator="type")
]

CLIENT_TYPES = frozenset({"ping", "pong", "subscribe", "unsubscribe"})
client_message_adapter: TypeAdapter[WsClientMessage] = TypeAdapter(WsClientMessage)
server_message_adapter: TypeAdapter[WsServerMessage] = TypeAdapter(WsServerMessage)

# Published in openapi.json under these names (ADR-0006: WS models live in components.schemas).
SCHEMA_UNIONS: dict[str, TypeAdapter[WsClientMessage] | TypeAdapter[WsServerMessage]] = {
    "WsClientMessage": client_message_adapter,
    "WsServerMessage": server_message_adapter,
}
