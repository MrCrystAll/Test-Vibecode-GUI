# SPDX-License-Identifier: Apache-2.0
"""WebSocket `/ws` (TC-20, T-19-4, T-20-1..5) against a real backend process.

Contract: apps/backend/README.md ("WebSocket /ws"): token as subprotocol `bearer.<token>` next to
`studio.v1`
(or an Authorization header), refused handshakes are HTTP 403, every message is the envelope
{type, version, id, ts, payload}, errors keep the connection open.
"""

from __future__ import annotations

import json
from contextlib import ExitStack, suppress
from datetime import datetime
from typing import Any

import httpx
import jsonschema
import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import ClientConnection, connect

from conftest import StartBackend
from harness.backend import REPO_ROOT, BackendProcess

SUBPROTOCOL = "studio.v1"
RECV_TIMEOUT = 5.0

_SCHEMAS: dict[str, Any] = json.loads(
    (REPO_ROOT / "packages/contract/openapi.json").read_text("utf-8")
)["components"]["schemas"]


def _validate(name: str, message: dict[str, Any]) -> None:
    schema = {"$ref": f"#/components/schemas/{name}", "components": {"schemas": _SCHEMAS}}
    jsonschema.validate(message, schema, format_checker=jsonschema.FormatChecker())


def _url(bp: BackendProcess) -> str:
    return f"ws://127.0.0.1:{bp.handshake.port}/ws"


def _open(bp: BackendProcess, token: str | None = "", **kwargs: Any) -> ClientConnection:
    """Connect like a browser would: token as subprotocol. `token=None` offers none at all."""
    real = bp.handshake.token if token == "" else token
    subprotocols = [SUBPROTOCOL] + ([f"bearer.{real}"] if real is not None else [])
    return connect(_url(bp), subprotocols=subprotocols, open_timeout=5, **kwargs)  # type: ignore[arg-type]


def _envelope(type_: str, payload: dict[str, Any] | None = None, id_: str = "qa-1") -> str:
    return json.dumps(
        {
            "type": type_,
            "version": 1,
            "id": id_,
            "ts": datetime.now().astimezone().isoformat(),
            "payload": payload or {},
        }
    )


def _recv(ws: ClientConnection) -> dict[str, Any]:
    message = json.loads(ws.recv(timeout=RECV_TIMEOUT))
    assert isinstance(message, dict)
    return message


def _recv_type(ws: ClientConnection, type_: str, limit: int = 10) -> dict[str, Any]:
    """Next message of this type (server pings may be interleaved)."""
    for _ in range(limit):
        message = _recv(ws)
        if message["type"] == type_:
            return message
    raise AssertionError(f"no {type_!r} message within {limit} messages")


@pytest.fixture
def fast_ping(start_backend_fn: StartBackend) -> BackendProcess:
    return start_backend_fn(args=["--ws-ping-interval", "0.2"])


def _rejected_status(bp: BackendProcess, **kwargs: Any) -> int:
    with pytest.raises(InvalidStatus) as excinfo:
        _open(bp, **kwargs)
    return excinfo.value.response.status_code


# --- AC1: authentication (T-19-4, T-20-1) -------------------------------------------------------


@pytest.mark.ac("TC-20", 1)
@pytest.mark.ac("TC-19", 3)
def test_ws_is_refused_without_a_token_or_with_a_wrong_one(backend: BackendProcess) -> None:
    assert _rejected_status(backend, token=None) == 403
    assert _rejected_status(backend, token="w" * 43) == 403


@pytest.mark.ac("TC-20", 1)
@pytest.mark.ac("TC-19", 3)
def test_ws_token_in_the_url_is_not_accepted(backend: BackendProcess) -> None:
    with pytest.raises(InvalidStatus) as excinfo:
        connect(
            f"{_url(backend)}?token={backend.handshake.token}",
            subprotocols=[SUBPROTOCOL],  # type: ignore[list-item]
            open_timeout=5,
        )
    assert excinfo.value.response.status_code == 403


@pytest.mark.ac("TC-20", 1)
def test_ws_accepts_the_token_as_subprotocol_and_echoes_studio_v1(backend: BackendProcess) -> None:
    with _open(backend) as ws:
        assert ws.subprotocol == SUBPROTOCOL  # the token itself is never echoed back


@pytest.mark.ac("TC-20", 1)
def test_ws_accepts_an_authorization_header_for_non_browser_clients(
    backend: BackendProcess,
) -> None:
    headers = {"Authorization": f"Bearer {backend.handshake.token}"}
    with connect(
        _url(backend),
        subprotocols=[SUBPROTOCOL],  # type: ignore[list-item]
        additional_headers=headers,
        open_timeout=5,
    ) as ws:
        ws.send(_envelope("ping"))
        assert _recv_type(ws, "pong")["payload"]["reply_to"] == "qa-1"


@pytest.mark.ac("TC-20", 1)
def test_ws_with_a_foreign_origin_is_refused_even_with_the_token(backend: BackendProcess) -> None:
    assert _rejected_status(backend, origin="http://evil.example") == 403


@pytest.mark.ac("TC-20", 1)
def test_ws_without_the_studio_subprotocol_is_closed_with_1008(backend: BackendProcess) -> None:
    token = backend.handshake.token
    try:
        ws = connect(_url(backend), subprotocols=[f"bearer.{token}"], open_timeout=5)  # type: ignore[list-item]
    except InvalidStatus as exc:
        assert exc.response.status_code == 403
        return
    with ws, pytest.raises(ConnectionClosed) as excinfo:
        ws.recv(timeout=RECV_TIMEOUT)
    assert excinfo.value.rcvd is not None
    assert excinfo.value.rcvd.code == 1008


# --- AC2/AC3: envelope, ping, pong (T-20-2, T-20-3) --------------------------------------------


@pytest.mark.ac("TC-20", 2)
@pytest.mark.ac("TC-20", 3)
def test_server_pings_at_the_configured_interval_and_every_message_matches_the_schema(
    fast_ping: BackendProcess,
) -> None:
    seen: list[dict[str, Any]] = []
    with _open(fast_ping) as ws:
        for _ in range(3):
            seen.append(_recv(ws))
    assert [m["type"] for m in seen] == ["ping", "ping", "ping"]
    for message in seen:
        _validate("WsServerMessage", message)
        assert message["version"] == 1
        assert message["payload"] == {}
        assert datetime.fromisoformat(message["ts"]).tzinfo is not None
    ids = [m["id"] for m in seen]
    assert len(set(ids)) == len(ids), "message ids must be unique"
    stamps = [datetime.fromisoformat(m["ts"]) for m in seen]
    assert stamps == sorted(stamps)


@pytest.mark.ac("TC-20", 3)
def test_client_ping_is_answered_with_a_pong_referencing_its_id(backend: BackendProcess) -> None:
    with _open(backend) as ws:
        ws.send(_envelope("ping", id_="qa-ping-7"))
        pong = _recv_type(ws, "pong")
        _validate("WsServerMessage", pong)
        assert pong["payload"] == {"reply_to": "qa-ping-7"}


@pytest.mark.ac("TC-20", 3)
def test_client_pong_is_accepted_silently_and_the_connection_stays_usable(
    backend: BackendProcess,
) -> None:
    with _open(backend) as ws:
        ws.send(_envelope("pong", {"reply_to": "x"}))
        ws.send(_envelope("pong"))
        ws.send(_envelope("ping", id_="after-pong"))
        assert _recv_type(ws, "pong")["payload"]["reply_to"] == "after-pong"


# --- AC4: topics (T-20-4) ----------------------------------------------------------------------


@pytest.mark.ac("TC-20", 4)
def test_subscribe_to_system_is_acknowledged_and_unsubscribe_too(backend: BackendProcess) -> None:
    with _open(backend) as ws:
        ws.send(_envelope("subscribe", {"topic": "system"}, id_="sub-1"))
        ack = _recv_type(ws, "subscribed")
        _validate("WsServerMessage", ack)
        assert ack["payload"] == {"topic": "system", "reply_to": "sub-1"}
        ws.send(_envelope("unsubscribe", {"topic": "system"}, id_="unsub-1"))
        gone = _recv_type(ws, "unsubscribed")
        _validate("WsServerMessage", gone)
        assert gone["payload"] == {"topic": "system", "reply_to": "unsub-1"}


@pytest.mark.ac("TC-20", 4)
def test_subscribe_to_an_unknown_topic_is_an_error_and_the_connection_stays_usable(
    backend: BackendProcess,
) -> None:
    with _open(backend) as ws:
        ws.send(_envelope("subscribe", {"topic": "nope"}, id_="sub-bad"))
        error = _recv_type(ws, "error")
        _validate("WsServerMessage", error)
        assert error["payload"]["code"] == "unknown_topic"
        assert error["payload"]["reply_to"] == "sub-bad"
        ws.send(_envelope("ping", id_="still-alive"))
        assert _recv_type(ws, "pong")["payload"]["reply_to"] == "still-alive"


# --- AC5: bad messages (T-20-5) ---------------------------------------------------------------


def _raw(**overrides: Any) -> str:
    base: dict[str, Any] = {"type": "ping", "version": 1, "id": "a", "ts": "x", "payload": {}}
    base.update(overrides)
    return json.dumps({k: v for k, v in base.items() if v is not ...})


BAD_MESSAGES: list[tuple[str, str, str]] = [
    ("not json", "{not json", "invalid_json"),
    ("json array", "[1, 2]", "invalid_envelope"),
    ("json string", '"hello"', "invalid_envelope"),
    ("missing type", _raw(type=...), "invalid_envelope"),
    ("missing payload", _raw(payload=...), "invalid_envelope"),
    ("wrong version", _raw(version=99), "unsupported_version"),
    ("unknown type", _raw(type="teleport"), "unknown_type"),
    ("payload is not an object", _raw(type="subscribe", payload=[]), "invalid_payload"),
    ("subscribe without topic", _raw(type="subscribe"), "invalid_payload"),
]


@pytest.mark.ac("TC-20", 5)
@pytest.mark.parametrize(("label", "raw", "code"), BAD_MESSAGES, ids=[b[0] for b in BAD_MESSAGES])
def test_bad_messages_get_a_documented_error_and_the_connection_stays_open(
    backend: BackendProcess, label: str, raw: str, code: str
) -> None:
    with _open(backend) as ws:
        ws.send(raw)
        error = _recv_type(ws, "error")
        _validate("WsServerMessage", error)
        assert error["payload"]["code"] == code, label
        ws.send(_envelope("ping", id_="after-bad"))
        assert _recv_type(ws, "pong")["payload"]["reply_to"] == "after-bad"


@pytest.mark.ac("TC-20", 5)
def test_a_binary_frame_does_not_kill_the_backend(
    backend: BackendProcess, client: httpx.Client
) -> None:
    with _open(backend) as ws:
        ws.send(b"\x00\x01\x02")
        with suppress(ConnectionClosed):  # closing is acceptable; dying is not
            _validate("WsServerMessage", _recv_type(ws, "error"))
    assert client.get("/api/version").status_code == 200


@pytest.mark.ac("TC-20", 5)
def test_an_oversized_message_closes_only_that_connection(
    backend: BackendProcess, client: httpx.Client
) -> None:
    huge = _envelope("ping", {"blob": "x" * (20 * 1024 * 1024)})
    with _open(backend, max_size=None) as victim, _open(backend) as bystander:
        try:
            victim.send(huge)
            assert json.loads(victim.recv(timeout=RECV_TIMEOUT))["type"] in {
                "error",
                "pong",
                "ping",
            }
        except ConnectionClosed:
            pass  # closing with 1009 (message too big) is the expected outcome
        bystander.send(_envelope("ping", id_="bystander"))
        assert _recv_type(bystander, "pong")["payload"]["reply_to"] == "bystander"
    assert client.get("/api/version").status_code == 200


@pytest.mark.ac("TC-20", 5)
def test_clients_are_independent_and_the_backend_keeps_serving(
    backend: BackendProcess, client: httpx.Client
) -> None:
    with ExitStack() as stack:
        opened = [stack.enter_context(_open(backend)) for _ in range(5)]
        for index, ws in enumerate(opened):
            ws.send(_envelope("ping", id_=f"c{index}"))
        for index, ws in enumerate(opened):
            assert _recv_type(ws, "pong")["payload"]["reply_to"] == f"c{index}"
        opened[0].close()
        opened[1].send("{broken")
        assert _recv_type(opened[1], "error")["payload"]["code"] == "invalid_json"
        opened[2].send(_envelope("ping", id_="last"))
        assert _recv_type(opened[2], "pong")["payload"]["reply_to"] == "last"
    assert client.get("/api/health").status_code == 200
