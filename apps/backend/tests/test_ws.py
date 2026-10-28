# SPDX-License-Identifier: Apache-2.0
"""TC-20: the /ws endpoint, its envelope, ping, subscriptions and error handling."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import pytest
from conftest import TEST_TOKEN
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from studio_backend.app import create_app
from studio_backend.events import server_message_adapter
from studio_backend.security import SecurityConfig

WS_URL = "ws://127.0.0.1:8000/ws"
SUBPROTOCOLS = ["studio.v1", f"bearer.{TEST_TOKEN}"]
LONG_INTERVAL = 3600.0  # tests that must not see a server ping


def _client(ping_interval: float = LONG_INTERVAL) -> TestClient:
    app = create_app(SecurityConfig(token=TEST_TOKEN), ws_ping_interval=ping_interval)
    return TestClient(app, base_url="http://127.0.0.1:8000")


@contextmanager
def _connect(ping_interval: float = LONG_INTERVAL) -> Iterator[WebSocketTestSession]:
    with _client(ping_interval).websocket_connect(WS_URL, subprotocols=SUBPROTOCOLS) as ws:
        yield ws


def _message(type_: str, payload: dict[str, Any] | None = None, **overrides: Any) -> str:
    message: dict[str, Any] = {
        "type": type_,
        "version": 1,
        "id": f"c-{type_}",
        "ts": "2026-10-27T10:00:00Z",
        "payload": {} if payload is None else payload,
    }
    message.update(overrides)
    return json.dumps(message)


def _receive(ws: WebSocketTestSession) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(ws.receive_text())
    server_message_adapter.validate_python(raw)  # every server message matches the contract
    return raw


# --- connecting and authenticating -----------------------------------------------------------


def test_connection_echoes_the_studio_subprotocol() -> None:
    with _connect() as ws:
        assert ws.accepted_subprotocol == "studio.v1"


def test_connection_without_studio_subprotocol_is_refused() -> None:
    client = _client()
    with (
        pytest.raises(WebSocketDisconnect) as refused,
        client.websocket_connect(WS_URL, subprotocols=[f"bearer.{TEST_TOKEN}"]),
    ):
        pass
    assert refused.value.code == 1008


@pytest.mark.parametrize("subprotocols", [["studio.v1"], ["studio.v1", "bearer.nope"]])
def test_connection_without_valid_token_is_refused(subprotocols: list[str]) -> None:
    client = _client()
    with (
        pytest.raises(WebSocketDisconnect) as refused,
        client.websocket_connect(WS_URL, subprotocols=subprotocols),
    ):
        pass
    assert refused.value.code == 1008


def test_authorization_header_works_for_non_browser_clients() -> None:
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
    with _client().websocket_connect(WS_URL, subprotocols=["studio.v1"], headers=headers) as ws:
        ws.send_text(_message("ping"))
        assert _receive(ws)["type"] == "pong"


# --- envelope and ping -----------------------------------------------------------------------


def test_server_pings_at_the_configured_interval() -> None:
    with _connect(ping_interval=0.05) as ws:
        first, second = _receive(ws), _receive(ws)

    for message in (first, second):
        assert set(message) == {"type", "version", "id", "ts", "payload"}
        assert message["type"] == "ping"
        assert message["version"] == 1
        assert message["payload"] == {}
        assert datetime.fromisoformat(message["ts"]).tzinfo is not None
    assert first["id"] != second["id"]


def test_client_ping_gets_a_pong_naming_it() -> None:
    with _connect() as ws:
        ws.send_text(_message("ping"))
        reply = _receive(ws)

    assert reply["type"] == "pong"
    assert reply["payload"] == {"reply_to": "c-ping"}


def test_client_pong_is_accepted_silently() -> None:
    with _connect() as ws:
        ws.send_text(_message("pong", {"reply_to": "s-1"}))
        ws.send_text(_message("ping"))  # the next reply is the pong, not an error
        assert _receive(ws)["type"] == "pong"


# --- subscriptions ---------------------------------------------------------------------------


def test_subscribe_and_unsubscribe_system_topic() -> None:
    with _connect() as ws:
        ws.send_text(_message("subscribe", {"topic": "system"}, id="c-sub"))
        subscribed = _receive(ws)
        ws.send_text(_message("unsubscribe", {"topic": "system"}, id="c-unsub"))
        unsubscribed = _receive(ws)

    assert subscribed["type"] == "subscribed"
    assert subscribed["payload"] == {"topic": "system", "reply_to": "c-sub"}
    assert unsubscribed["type"] == "unsubscribed"
    assert unsubscribed["payload"] == {"topic": "system", "reply_to": "c-unsub"}


# --- rejecting bad messages ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("not json", "invalid_json"),
        ("[1, 2]", "invalid_envelope"),
        (json.dumps({"version": 1}), "invalid_envelope"),
        (json.dumps({"type": "ping", "version": 1, "id": "x"}), "invalid_envelope"),
        (_message("ping", version=2), "unsupported_version"),
        (_message("launch_missiles"), "unknown_type"),
        (_message("subscribe", {"topic": "runs"}), "unknown_topic"),
        (_message("subscribe", {}), "invalid_payload"),
        (_message("ping", {"extra": True}), "invalid_payload"),
        (_message("ping", ts="yesterday"), "invalid_payload"),
        (_message("ping", surprise=1), "invalid_payload"),
    ],
)
def test_bad_message_gets_an_error_and_the_connection_stays_open(text: str, code: str) -> None:
    with _connect() as ws:
        ws.send_text(text)
        error = _receive(ws)
        ws.send_text(_message("ping"))
        still_open = _receive(ws)

    assert error["type"] == "error"
    assert error["payload"]["code"] == code
    assert error["payload"]["message"]
    assert still_open["type"] == "pong"


def test_error_names_the_rejected_message_when_it_has_an_id() -> None:
    with _connect() as ws:
        ws.send_text(_message("launch_missiles", id="c-42"))
        error = _receive(ws)

    assert error["payload"]["reply_to"] == "c-42"


# --- contract --------------------------------------------------------------------------------


def test_websocket_models_are_published_in_the_openapi_schema() -> None:
    schemas = create_app().openapi()["components"]["schemas"]

    client = schemas["WsClientMessage"]
    server = schemas["WsServerMessage"]
    assert set(client["discriminator"]["mapping"]) == {"ping", "pong", "subscribe", "unsubscribe"}
    assert set(server["discriminator"]["mapping"]) == {
        "ping",
        "pong",
        "subscribed",
        "unsubscribed",
        "error",
    }
    for name in ("WsPing", "WsSubscribe", "WsError"):
        assert set(schemas[name]["required"]) == {"type", "version", "id", "ts", "payload"}
