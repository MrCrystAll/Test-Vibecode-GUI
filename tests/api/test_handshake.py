# SPDX-License-Identifier: Apache-2.0
"""Process contract: handshake, stdout/stderr discipline, settings (T-17-3, T-17-4, T-30-1)."""

from collections.abc import Callable

import httpx
import pytest

from conftest import StartBackend
from harness.backend import BackendProcess


@pytest.mark.ac("TC-17", 4)
@pytest.mark.ac("TC-30", 1)
def test_handshake_is_first_stdout_line_with_a_free_port(backend: BackendProcess) -> None:
    assert backend.handshake.raw["event"] == "listening"
    assert backend.handshake.port > 0


@pytest.mark.ac("TC-17", 4)
def test_two_backends_get_different_ports(start_backend_fn: StartBackend) -> None:
    first, second = start_backend_fn(), start_backend_fn()

    assert first.handshake.port != second.handshake.port


@pytest.mark.ac("TC-17", 3)
def test_logs_are_json_lines_on_stderr_and_stdout_has_only_the_handshake(
    start_backend_fn: StartBackend, client_for: Callable[[BackendProcess], httpx.Client]
) -> None:
    bp = start_backend_fn(args=["--log-level", "debug"])
    client_for(bp).get("/api/health")
    bp.stop()

    logs = bp.stderr_json()
    assert logs, "expected at least one log line"
    assert all({"level", "message"} <= set(entry) for entry in logs)
    assert bp.stdout_lines == []


@pytest.mark.ac("TC-17", 3)
def test_cli_log_level_beats_environment(start_backend_fn: StartBackend) -> None:
    bp = start_backend_fn(
        args=["--log-level", "warning"], env={"STUDIO_BACKEND_LOG_LEVEL": "debug"}
    )
    bp.stop()

    levels = {str(entry["level"]).lower() for entry in bp.stderr_json()}
    assert not levels & {"debug", "info"}
