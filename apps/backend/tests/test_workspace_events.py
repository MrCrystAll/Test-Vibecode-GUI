# SPDX-License-Identifier: Apache-2.0
"""Workspace WS events (TC-35 AC3): topic `workspace`, published by the stub on every change."""

import json
import os
from typing import Any

from conftest import TEST_TOKEN
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from studio_backend import openapi
from studio_backend.app import create_app
from studio_backend.events import TOPICS, server_message_adapter
from studio_backend.security import SecurityConfig

WS_URL = "ws://127.0.0.1:8000/ws"
SUBPROTOCOLS = ["studio.v1", f"bearer.{TEST_TOKEN}"]
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
WORKSPACE = os.path.abspath(os.path.join(os.sep, "tmp", "ws-events"))
EVENT_TYPES = {
    "project.created",
    "project.updated",
    "project.deleted",
    "workspace.changed",
    "workspace.rescanned",
}


def _receive(ws: WebSocketTestSession) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(ws.receive_text())
    server_message_adapter.validate_python(raw)
    return raw


def _subscribe(ws: WebSocketTestSession, topic: str) -> None:
    ws.send_text(
        json.dumps(
            {
                "type": "subscribe",
                "version": 1,
                "id": f"sub-{topic}",
                "ts": "2026-11-04T10:00:00Z",
                "payload": {"topic": topic},
            }
        )
    )
    assert _receive(ws)["type"] == "subscribed"


def test_workspace_is_a_topic_and_the_events_are_published() -> None:
    schemas = openapi.build_schema()["components"]["schemas"]
    published = {option["$ref"].rsplit("/", 1)[1] for option in schemas["WsServerMessage"]["oneOf"]}

    assert "workspace" in TOPICS
    assert {
        "WsProjectCreated",
        "WsProjectUpdated",
        "WsProjectDeleted",
        "WsWorkspaceChanged",
        "WsWorkspaceRescanned",
    } <= published
    mapping = schemas["WsServerMessage"]["discriminator"]["mapping"]
    assert set(mapping) >= EVENT_TYPES


def test_subscribers_get_every_change_with_source_app() -> None:
    app = create_app(SecurityConfig(token=TEST_TOKEN), ws_ping_interval=3600.0)
    with (
        TestClient(app, base_url="http://127.0.0.1:8000", headers=AUTH) as client,
        client.websocket_connect(WS_URL, subprotocols=SUBPROTOCOLS) as ws,
    ):
        _subscribe(ws, "workspace")

        client.post("/api/workspace/open", json={"path": WORKSPACE})
        client.post("/api/projects", json={"name": "Alpha"})
        client.patch("/api/projects/alpha", json={"name": "Alpha 2"})
        client.patch("/api/projects/alpha", json={})  # no change: no event
        client.delete("/api/projects/alpha")
        events = [_receive(ws) for _ in range(4)]

    assert [(event["type"], event["payload"]) for event in events] == [
        ("workspace.changed", {"path": WORKSPACE, "source": "app"}),
        ("project.created", {"project_id": "alpha", "source": "app"}),
        ("project.updated", {"project_id": "alpha", "source": "app"}),
        ("project.deleted", {"project_id": "alpha", "source": "app"}),
    ]


def test_sessions_not_subscribed_to_workspace_get_nothing() -> None:
    app = create_app(SecurityConfig(token=TEST_TOKEN), ws_ping_interval=3600.0)
    with (
        TestClient(app, base_url="http://127.0.0.1:8000", headers=AUTH) as client,
        client.websocket_connect(WS_URL, subprotocols=SUBPROTOCOLS) as ws,
    ):
        _subscribe(ws, "system")
        client.post("/api/workspace/open", json={"path": WORKSPACE})
        ws.send_text(
            json.dumps(
                {
                    "type": "ping",
                    "version": 1,
                    "id": "probe",
                    "ts": "2026-11-04T10:00:00Z",
                    "payload": {},
                }
            )
        )

        # The pong is the next message: no workspace event was queued before it.
        assert _receive(ws)["type"] == "pong"
