# SPDX-License-Identifier: Apache-2.0
"""System routes through the public HTTP contract (test plan T-17-1, T-17-2, T-30-4)."""

import httpx
import pytest


@pytest.mark.ac("TC-17", 1)
def test_health_returns_ok(client: httpx.Client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.ac("TC-17", 2)
def test_version_returns_app_and_api_versions(client: httpx.Client) -> None:
    response = client.get("/api/version")

    assert response.status_code == 200
    body = response.json()
    for key in ("app_version", "api_version"):
        assert isinstance(body[key], str) and body[key]
