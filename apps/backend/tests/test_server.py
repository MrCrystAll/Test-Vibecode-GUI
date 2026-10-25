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

    assert set(event) == {"event", "port"}
    assert event["event"] == "listening"
    assert isinstance(event["port"], int) and event["port"] > 0
    response = httpx.get(f"http://127.0.0.1:{event['port']}/api/health", timeout=5)
    assert response.json() == {"status": "ok"}


def test_stderr_carries_json_logs(backend: BackendProcess) -> None:
    backend.first_stdout_line()
    backend.stop()

    lines = [line for line in backend.stderr_lines() if line.strip()]
    assert lines
    for line in lines:
        assert "level" in json.loads(line)


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
