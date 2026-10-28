# SPDX-License-Identifier: Apache-2.0
"""Start the real backend process and check its stdout handshake (used by Electron)."""

import io
import json
import queue
import subprocess
import sys
import threading
from collections.abc import Iterator

import httpx
import pytest
from websockets.sync.client import connect as ws_connect

from studio_backend.server import announce

STARTUP_TIMEOUT_S = 30


class BackendProcess:
    def __init__(self, *args: str) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-m", "studio_backend", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._stdout_lines: queue.Queue[str] = queue.Queue()
        self._stderr: list[str] = []
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()

    def _pump_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self._stdout_lines.put(line)

    def _pump_stderr(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self._stderr.append(line)

    def first_stdout_line(self) -> str:
        try:
            return self._stdout_lines.get(timeout=STARTUP_TIMEOUT_S)
        except queue.Empty:
            pytest.fail(f"no handshake line; stderr was:\n{''.join(self._stderr)}")

    def stderr_lines(self) -> list[str]:
        return list(self._stderr)

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(timeout=STARTUP_TIMEOUT_S)


@pytest.fixture
def backend() -> Iterator[BackendProcess]:
    process = BackendProcess("--port", "0")
    yield process
    process.stop()


def test_port_zero_announces_the_bound_port_as_first_stdout_line(
    backend: BackendProcess,
) -> None:
    event = json.loads(backend.first_stdout_line())

    assert set(event) == {"event", "port", "token", "pid"}
    assert event["event"] == "listening"
    assert isinstance(event["port"], int) and event["port"] > 0
    assert isinstance(event["pid"], int) and event["pid"] > 0
    if sys.platform != "win32":
        # On Windows a venv's python.exe is a launcher that starts the real interpreter as a
        # child, which is exactly why the handshake reports its own pid.
        assert event["pid"] == backend.process.pid
    base = f"http://127.0.0.1:{event['port']}"
    assert httpx.get(f"{base}/api/health", timeout=5).json() == {"status": "ok"}
    assert httpx.get(f"{base}/api/version", timeout=5).status_code == 401
    authorized = {"Authorization": f"Bearer {event['token']}"}
    assert httpx.get(f"{base}/api/version", headers=authorized, timeout=5).status_code == 200


def test_real_server_speaks_websocket_on_ws() -> None:
    """/ws over a real socket, not Starlette's in-process TestClient (DEV-B's finding on TC-20).

    Fails if uvicorn has no WebSocket implementation installed.
    """
    process = BackendProcess("--port", "0", "--ws-ping-interval", "0.1")
    try:
        event = json.loads(process.first_stdout_line())
        url = f"ws://127.0.0.1:{event['port']}/ws"
        subprotocols = ["studio.v1", f"bearer.{event['token']}"]
        with ws_connect(url, subprotocols=subprotocols, open_timeout=5) as ws:  # type: ignore[arg-type]
            assert ws.subprotocol == "studio.v1"
            assert json.loads(ws.recv(timeout=5))["type"] == "ping"  # server ping
            client_ping = {
                "type": "ping",
                "version": 1,
                "id": "c-1",
                "ts": "2026-10-28T10:00:00Z",
                "payload": {},
            }
            ws.send(json.dumps(client_ping))
            replies = [json.loads(ws.recv(timeout=5)) for _ in range(3)]
        assert {"type": "pong", "reply_to": "c-1"} in [
            {"type": r["type"], "reply_to": r["payload"].get("reply_to")} for r in replies
        ]
    finally:
        process.stop()


def test_stderr_carries_json_logs_without_the_token(backend: BackendProcess) -> None:
    event = json.loads(backend.first_stdout_line())
    base = f"http://127.0.0.1:{event['port']}"
    httpx.get(f"{base}/api/version?token={event['token']}", timeout=5)  # lands in the access log
    backend.stop()

    lines = [line for line in backend.stderr_lines() if line.strip()]
    assert lines
    for line in lines:
        assert "level" in json.loads(line)
    assert event["token"] not in "".join(lines)
    assert any("token=***" in line for line in lines)


def test_two_instances_get_different_ports(backend: BackendProcess) -> None:
    other = BackendProcess("--port", "0")
    try:
        first = json.loads(backend.first_stdout_line())["port"]
        second = json.loads(other.first_stdout_line())["port"]
    finally:
        other.stop()

    assert first != second


def test_invalid_setting_exits_with_usage_error() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "studio_backend", "--port", "nope"],
        capture_output=True,
        text=True,
        timeout=STARTUP_TIMEOUT_S,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "--port" in result.stderr


def test_announce_writes_one_compact_json_line() -> None:
    stream = io.StringIO()

    announce({"event": "listening", "port": 1234}, stream=stream)

    assert stream.getvalue() == '{"event":"listening","port":1234}\n'
