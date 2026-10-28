# SPDX-License-Identifier: Apache-2.0
"""Local security through the public contract (test plan T-19-1..T-19-6, exit criterion X-4).

Only the documented surface is used: the command line, the handshake line, HTTP headers and the
logs. The route list comes from the committed `packages/contract/openapi.json` (a public contract
artefact), so a route added later is checked automatically.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from typing import Any

import httpx
import psutil
import pytest

from conftest import StartBackend
from harness.backend import REPO_ROOT, BackendProcess, backend_command

PUBLIC_PATHS = {"/api/health"}
ALLOWED_ORIGIN = "http://localhost:4200"
EVIL_ORIGIN = "http://evil.example"
TOKEN_ALPHABET = re.compile(r"[A-Za-z0-9_\-.~]+")
MIN_TOKEN_CHARS = 22  # 22 base64url characters = 132 bits, the ticket's lower bound is 128 bits


def _routes() -> list[tuple[str, str]]:
    schema = json.loads((REPO_ROOT / "packages/contract/openapi.json").read_text("utf-8"))
    methods = {"get", "post", "put", "patch", "delete"}
    return [
        (method.upper(), re.sub(r"\{[^}]+\}", "x", path))
        for path, item in schema["paths"].items()
        for method in item
        if method in methods
    ]


def _anonymous(bp: BackendProcess) -> httpx.Client:
    """A client that sends no credentials at all (unlike the shared `client`)."""
    return httpx.Client(base_url=bp.base_url, timeout=10.0)


def _bearer(token: str, scheme: str = "Bearer") -> dict[str, str]:
    return {"Authorization": f"{scheme} {token}"}


def _error_code(response: httpx.Response) -> str:
    body: dict[str, Any] = response.json()
    return str(body["error"]["code"])


# --- AC1: localhost-only binding --------------------------------------------------------------


@pytest.mark.ac("TC-19", 1)
def test_backend_listens_on_127_0_0_1_only(backend: BackendProcess) -> None:
    sockets = psutil.Process(backend.handshake.pid).net_connections(kind="tcp")
    listening = [c.laddr for c in sockets if c.status == psutil.CONN_LISTEN]

    assert [(a.ip, a.port) for a in listening] == [("127.0.0.1", backend.handshake.port)]


@pytest.mark.ac("TC-19", 1)
@pytest.mark.parametrize("host", ["0.0.0.0", "127.0.0.2"])  # noqa: S104 - the point of the test
def test_other_interface_is_refused_without_the_dev_flag(host: str) -> None:
    result = subprocess.run(
        [*backend_command(), "--port", "0", "--host", host],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        stdin=subprocess.DEVNULL,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout.strip() == "", "no handshake may be printed for a refused start"
    assert "unsafe" in result.stderr.lower()


@pytest.mark.ac("TC-19", 1)
def test_other_interface_starts_with_the_dev_flag_and_warns(start_backend_fn: StartBackend) -> None:
    # 127.0.0.2 is "another interface" for the backend but never leaves the machine.
    bp = start_backend_fn(args=["--host", "127.0.0.2", "--unsafe-bind-any"])
    bp.stop()

    levels = {str(e["level"]).lower() for e in bp.stderr_json()}
    assert "warning" in levels


# --- AC2: handshake and token -----------------------------------------------------------------


@pytest.mark.ac("TC-19", 2)
def test_handshake_has_port_token_and_the_serving_pid(backend: BackendProcess) -> None:
    raw = backend.handshake.raw

    assert raw["event"] == "listening"
    assert isinstance(raw["port"], int) and raw["port"] > 0
    assert isinstance(raw["token"], str)
    assert isinstance(raw["pid"], int)
    process = psutil.Process(raw["pid"])
    assert "studio_backend" in " ".join(process.cmdline()), "pid must be the serving python"
    assert raw["pid"] in backend.pids, "pid must belong to the spawned process tree"


@pytest.mark.ac("TC-19", 2)
def test_token_is_long_url_safe_and_different_on_every_launch(
    start_backend_fn: StartBackend,
) -> None:
    first, second = start_backend_fn(), start_backend_fn()

    for token in (first.handshake.token, second.handshake.token):
        assert token is not None
        assert len(token) >= MIN_TOKEN_CHARS
        assert TOKEN_ALPHABET.fullmatch(token)
    assert first.handshake.token != second.handshake.token


@pytest.mark.ac("TC-19", 2)
def test_token_from_environment_is_used(
    start_backend_fn: StartBackend, client_for: Callable[[BackendProcess], httpx.Client]
) -> None:
    token = "qa-fixed-token_0123456789.abcdefghij~KLMNOP"  # noqa: S105 - a throwaway test token
    bp = start_backend_fn(env={"STUDIO_BACKEND_TOKEN": token})

    assert bp.handshake.token == token
    assert client_for(bp).get("/api/version").status_code == 200
    with _anonymous(bp) as anon:
        assert anon.get("/api/version", headers=_bearer("x" * 40)).status_code == 401


@pytest.mark.ac("TC-19", 2)
@pytest.mark.parametrize("bad", ["short", "has space " * 5, "ünïcödé-" * 6])
def test_invalid_token_from_environment_is_refused(bad: str) -> None:
    result = subprocess.run(
        [*backend_command(), "--port", "0"],
        cwd=REPO_ROOT,
        env={**os.environ, "STUDIO_BACKEND_TOKEN": bad},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        stdin=subprocess.DEVNULL,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout.strip() == ""
    assert bad not in result.stderr, "a rejected token must not be echoed"


# --- AC3: token required on every route but /api/health -----------------------------------------


@pytest.mark.ac("TC-19", 3)
@pytest.mark.ac("TC-19", 6)
@pytest.mark.parametrize(("method", "path"), _routes(), ids=lambda v: str(v))
def test_route_requires_the_token(backend: BackendProcess, method: str, path: str) -> None:
    token = backend.handshake.token
    assert token is not None
    with _anonymous(backend) as anon:
        no_header = anon.request(method, path)
        wrong = anon.request(method, path, headers=_bearer("w" * 43))
        basic = anon.request(method, path, headers=_bearer(token, scheme="Basic"))
        right = anon.request(method, path, headers=_bearer(token))

    if path in PUBLIC_PATHS:
        assert no_header.status_code == 200
        return
    for rejected in (no_header, wrong, basic):
        assert rejected.status_code == 401
        assert rejected.headers["www-authenticate"] == "Bearer"
        assert _error_code(rejected) == "unauthorized"
    assert right.status_code != 401
    if method == "GET" and "x" not in path.split("/")[-1:]:
        assert right.status_code == 200


@pytest.mark.ac("TC-19", 3)
@pytest.mark.parametrize("path", ["/api/does-not-exist", "/openapi.json", "/docs", "/"])
def test_unknown_and_documentation_routes_also_need_the_token(
    backend: BackendProcess, path: str
) -> None:
    with _anonymous(backend) as anon:
        assert anon.get(path).status_code == 401


@pytest.mark.ac("TC-19", 3)
def test_token_in_the_query_string_is_not_accepted_over_http(backend: BackendProcess) -> None:
    with _anonymous(backend) as anon:
        response = anon.get("/api/version", params={"token": backend.handshake.token})

    assert response.status_code == 401


# --- AC4: Host check and CORS ----------------------------------------------------------------


@pytest.mark.ac("TC-19", 4)
@pytest.mark.ac("TC-19", 6)
def test_foreign_host_header_is_rejected_even_with_the_token(backend: BackendProcess) -> None:
    token = backend.handshake.token
    assert token is not None
    port = backend.handshake.port
    with _anonymous(backend) as anon:
        rebound = anon.get(
            "/api/version", headers={**_bearer(token), "Host": f"evil.example:{port}"}
        )
        local = anon.get("/api/version", headers={**_bearer(token), "Host": f"localhost:{port}"})
        ipv4 = anon.get("/api/version", headers={**_bearer(token), "Host": f"127.0.0.1:{port}"})

    assert rebound.status_code == 400 and _error_code(rebound) == "invalid_host"
    assert local.status_code == 200
    assert ipv4.status_code == 200


@pytest.mark.ac("TC-19", 4)
@pytest.mark.ac("TC-19", 6)
def test_non_allowed_origin_is_rejected_even_with_the_token(
    backend: BackendProcess, client: httpx.Client
) -> None:
    response = client.get("/api/version", headers={"Origin": EVIL_ORIGIN})
    health = client.get("/api/health", headers={"Origin": EVIL_ORIGIN})

    assert response.status_code == 403 and _error_code(response) == "origin_not_allowed"
    assert health.status_code == 403, "the public health route is not exempt from the origin check"
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.ac("TC-19", 4)
def test_allowed_origin_gets_cors_headers_and_preflight_needs_no_token(
    start_backend_fn: StartBackend, client_for: Callable[[BackendProcess], httpx.Client]
) -> None:
    bp = start_backend_fn(args=["--allowed-origin", ALLOWED_ORIGIN])
    client = client_for(bp)
    preflight_headers = {
        "Origin": ALLOWED_ORIGIN,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    }
    with _anonymous(bp) as anon:
        preflight = anon.options("/api/version", headers=preflight_headers)
        evil_preflight = anon.options(
            "/api/version", headers={**preflight_headers, "Origin": EVIL_ORIGIN}
        )
    call = client.get("/api/version", headers={"Origin": ALLOWED_ORIGIN})

    assert preflight.status_code in (200, 204)
    assert preflight.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "authorization" in preflight.headers["access-control-allow-headers"].lower()
    assert evil_preflight.status_code == 403
    assert call.status_code == 200
    assert call.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


@pytest.mark.ac("TC-19", 4)
def test_without_configuration_no_origin_is_allowed(client: httpx.Client) -> None:
    response = client.get("/api/version", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 403


# --- AC5: the token never reaches the logs ------------------------------------------------------


@pytest.mark.ac("TC-19", 5)
def test_token_is_never_logged_or_printed_after_the_handshake(
    start_backend_fn: StartBackend, client_for: Callable[[BackendProcess], httpx.Client]
) -> None:
    bp = start_backend_fn(args=["--log-level", "debug", "--allowed-origin", ALLOWED_ORIGIN])
    token = bp.handshake.token
    assert token is not None
    client = client_for(bp)
    client.get("/api/version")
    client.get("/api/version", params={"token": token})  # the query form is refused over HTTP
    client.get("/api/version", headers={**_bearer("w" * 43)})
    client.get("/api/does-not-exist")
    client.get("/api/version", headers={"Origin": EVIL_ORIGIN})
    client.get("/api/version", headers={"Host": "evil.example"})
    bp.stop()

    assert token not in "\n".join(bp.stderr_lines)
    assert token not in "\n".join(bp.stdout_lines)
    log_lines = bp.log_path.read_text("utf-8").splitlines()
    leaked = [line for line in log_lines if token in line and not line.startswith("OUT ")]
    assert leaked == []
    assert any(token in line for line in log_lines if line.startswith("OUT ")), (
        "sanity check: the handshake line itself (stdout) does carry the token"
    )
