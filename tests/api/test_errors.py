# SPDX-License-Identifier: Apache-2.0
"""One JSON error shape for every error response (test plan T-17-8)."""

import httpx
import pytest


def assert_error_shape(body: object, code: str) -> None:
    assert isinstance(body, dict) and set(body) == {"error"}
    error = body["error"]
    assert set(error) >= {"code", "message", "details"}
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]


@pytest.mark.ac("TC-17", 7)
def test_unknown_route_returns_not_found_error(client: httpx.Client) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert_error_shape(response.json(), "not_found")


@pytest.mark.ac("TC-17", 7)
def test_wrong_method_returns_method_not_allowed_error(client: httpx.Client) -> None:
    response = client.post("/api/health", json={})

    assert response.status_code == 405
    assert_error_shape(response.json(), "method_not_allowed")
