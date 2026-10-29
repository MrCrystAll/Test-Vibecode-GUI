# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio_backend.app import create_app
from studio_backend.security import SecurityConfig

TEST_TOKEN = "test-token-0123456789-abcdefghijklmnop"  # noqa: S105 - test value
TEST_ORIGIN = "http://localhost:4200"


def make_app() -> FastAPI:
    return create_app(SecurityConfig(token=TEST_TOKEN, allowed_origins=(TEST_ORIGIN,)))


def authorized_client(app: FastAPI, raise_server_exceptions: bool = True) -> TestClient:
    """A client that talks to `app` like the UI does: loopback Host and the bearer token."""
    return TestClient(
        app,
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        raise_server_exceptions=raise_server_exceptions,
    )


@pytest.fixture
def client() -> TestClient:
    return authorized_client(make_app())


@pytest.fixture
def anonymous_client() -> TestClient:
    """Loopback Host, no token."""
    return TestClient(make_app(), base_url="http://127.0.0.1:8000")
