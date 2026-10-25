# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the black-box API suite. See README.md for the conventions."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from harness.backend import BackendError, BackendProcess, start_backend
from harness.paths import hostile_dir

StartBackend = Callable[..., BackendProcess]


def _client(backend: BackendProcess) -> httpx.Client:
    headers = {}
    if backend.handshake.token is not None:
        headers["Authorization"] = f"Bearer {backend.handshake.token}"
    return httpx.Client(base_url=backend.base_url, headers=headers, timeout=10.0)


@pytest.fixture(scope="session")
def backend(tmp_path_factory: pytest.TempPathFactory) -> Iterator[BackendProcess]:
    """One backend shared by read-only tests; tests that change state use `start_backend_fn`."""
    bp = start_backend(tmp_path_factory.mktemp("backend-logs"))
    yield bp
    bp.stop()


@pytest.fixture(scope="session")
def client(backend: BackendProcess) -> Iterator[httpx.Client]:
    """HTTP client for the shared backend, with the per-launch token when the handshake has one."""
    with _client(backend) as c:
        yield c


@pytest.fixture
def start_backend_fn(tmp_path: Path) -> Iterator[StartBackend]:
    """Start backends for this test (own args/env); all are stopped and checked at teardown."""
    started: list[BackendProcess] = []

    def start(args: list[str] | None = None, env: dict[str, str] | None = None) -> BackendProcess:
        bp = start_backend(tmp_path / "backend-logs", args=args, env=env)
        started.append(bp)
        return bp

    yield start
    errors: list[BackendError] = []
    for bp in started:
        try:
            bp.stop()
        except BackendError as exc:
            errors.append(exc)
    if errors:
        raise BackendError("; ".join(str(e) for e in errors))


@pytest.fixture
def client_for() -> Iterator[Callable[[BackendProcess], httpx.Client]]:
    """HTTP clients for backends started with `start_backend_fn`, closed at teardown."""
    clients: list[httpx.Client] = []

    def make(bp: BackendProcess) -> httpx.Client:
        c = _client(bp)
        clients.append(c)
        return c

    yield make
    for c in clients:
        c.close()


@pytest.fixture
def hostile_tmp(tmp_path: Path) -> Path:
    """A fresh temp dir whose path contains a space and non-ASCII characters."""
    return hostile_dir(tmp_path)
