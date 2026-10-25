# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from studio_backend.app import create_app


def _test_app_client() -> TestClient:
    """The real app plus two test-only routes that trigger a 422 and a 500."""
    app = create_app()

    @app.get("/test/items/{item_id}")
    def get_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/test/crash")
    def crash() -> None:
        raise RuntimeError("boom")

    return TestClient(app, raise_server_exceptions=False)


def _assert_error_shape(body: dict[str, object], code: str) -> None:
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == code
    assert isinstance(error["message"], str)


def test_unknown_route_returns_not_found_error(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    _assert_error_shape(response.json(), "not_found")


def test_wrong_method_returns_method_not_allowed_error(client: TestClient) -> None:
    response = client.post("/api/health")

    assert response.status_code == 405
    _assert_error_shape(response.json(), "method_not_allowed")


def test_invalid_input_returns_validation_error_with_details() -> None:
    response = _test_app_client().get("/test/items/not-a-number")

    assert response.status_code == 422
    body = response.json()
    _assert_error_shape(body, "validation_error")
    assert body["error"]["details"][0]["loc"] == ["path", "item_id"]


def test_unhandled_exception_returns_internal_error_without_leaking_details() -> None:
    response = _test_app_client().get("/test/crash")

    assert response.status_code == 500
    body = response.json()
    _assert_error_shape(body, "internal_error")
    assert "boom" not in response.text
