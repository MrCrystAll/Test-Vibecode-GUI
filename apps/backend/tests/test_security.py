# SPDX-License-Identifier: Apache-2.0
"""TC-19: loopback Host, allowed Origins and the bearer token, over HTTP and WebSocket."""

import pytest
from conftest import TEST_ORIGIN, TEST_TOKEN, make_app
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from studio_backend.app import create_app
from studio_backend.security import SecurityConfig, generate_token

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000"  # websocket_connect ignores base_url
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


def _error_code(response: object) -> str:
    return response.json()["error"]["code"]  # type: ignore[attr-defined, no-any-return]


@pytest.fixture
def http() -> TestClient:
    return TestClient(make_app(), base_url=BASE_URL)


def test_health_needs_no_token(http: TestClient) -> None:
    assert http.get("/api/health").status_code == 200


def test_missing_token_is_401(http: TestClient) -> None:
    response = http.get("/api/version")

    assert response.status_code == 401
    assert _error_code(response) == "unauthorized"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "authorization",
    [
        f"Bearer {TEST_TOKEN}x",
        f"Bearer {TEST_TOKEN[:-1]}",
        f"Basic {TEST_TOKEN}",
        TEST_TOKEN,
        "Bearer ",
    ],
)
def test_wrong_token_is_401(http: TestClient, authorization: str) -> None:
    response = http.get("/api/version", headers={"Authorization": authorization})

    assert response.status_code == 401


def test_right_token_is_200(http: TestClient) -> None:
    assert http.get("/api/version", headers=AUTH).status_code == 200


def test_query_token_is_not_accepted_over_http(http: TestClient) -> None:
    assert http.get(f"/api/version?token={TEST_TOKEN}").status_code == 401


def test_unknown_routes_and_openapi_need_the_token_too(http: TestClient) -> None:
    # Unauthenticated callers must not learn which routes exist.
    assert http.get("/api/nope").status_code == 401
    assert http.get("/openapi.json").status_code == 401
    assert http.get("/docs").status_code == 401


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8000", "192.168.1.10:8000", ""])
def test_non_loopback_host_header_is_rejected(http: TestClient, host: str) -> None:
    # DNS rebinding: a page on evil.example resolved to 127.0.0.1 still sends its own Host.
    response = http.get("/api/health", headers={"Host": host})

    assert response.status_code == 400
    assert _error_code(response) == "invalid_host"


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.1:1234", "localhost:4321", "LOCALHOST"])
def test_loopback_host_header_is_accepted(http: TestClient, host: str) -> None:
    assert http.get("/api/health", headers={"Host": host}).status_code == 200


def test_allowed_origin_gets_cors_headers(http: TestClient) -> None:
    response = http.get("/api/version", headers={**AUTH, "Origin": TEST_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == TEST_ORIGIN


@pytest.mark.parametrize("origin", ["http://evil.example", "null", "http://localhost:4201"])
def test_non_allowed_origin_is_rejected_even_with_the_token(http: TestClient, origin: str) -> None:
    response = http.get("/api/version", headers={**AUTH, "Origin": origin})

    assert response.status_code == 403
    assert _error_code(response) == "origin_not_allowed"
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_from_allowed_origin_needs_no_token(http: TestClient) -> None:
    response = http.options(
        "/api/version",
        headers={
            "Origin": TEST_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == TEST_ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_cors_preflight_from_other_origin_is_rejected(http: TestClient) -> None:
    response = http.options(
        "/api/version",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 403


def test_default_app_is_locked_with_an_unknown_token() -> None:
    client = TestClient(create_app(), base_url=BASE_URL)

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/version", headers=AUTH).status_code == 401


def test_generated_token_has_at_least_128_bits() -> None:
    assert len(generate_token()) * 6 >= 128


def test_token_is_not_in_the_config_repr() -> None:
    assert TEST_TOKEN not in repr(SecurityConfig(token=TEST_TOKEN))


# --- WebSocket (the /ws endpoint itself arrives with TC-20) --------------------------------------


def _ws_app() -> FastAPI:
    app = make_app()

    @app.websocket("/test/ws")
    async def echo(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text("hello")
        await websocket.close()

    return app


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        (f"{WS_URL}/test/ws?token={TEST_TOKEN}", {}),
        (f"{WS_URL}/test/ws", AUTH),
        (f"{WS_URL}/test/ws?token={TEST_TOKEN}", {"Origin": TEST_ORIGIN}),
    ],
)
def test_websocket_with_token_connects(path: str, headers: dict[str, str]) -> None:
    client = TestClient(_ws_app(), base_url=BASE_URL)

    with client.websocket_connect(path, headers=headers) as ws:
        assert ws.receive_text() == "hello"


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        (f"{WS_URL}/test/ws", {}),
        (f"{WS_URL}/test/ws?token=wrong", {}),
        (f"{WS_URL}/test/ws?token={TEST_TOKEN}", {"Origin": "http://evil.example"}),
        (f"{WS_URL}/test/ws?token={TEST_TOKEN}", {"Host": "evil.example"}),
    ],
)
def test_websocket_without_token_or_from_bad_origin_is_refused(
    path: str, headers: dict[str, str]
) -> None:
    client = TestClient(_ws_app(), base_url=BASE_URL)

    with (
        pytest.raises(WebSocketDisconnect) as refused,
        client.websocket_connect(path, headers=headers),
    ):
        pass
    assert refused.value.code == 1008
