# SPDX-License-Identifier: Apache-2.0
from importlib.metadata import version

from fastapi.testclient import TestClient

from studio_backend.version import API_VERSION


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_returns_package_and_api_versions(client: TestClient) -> None:
    response = client.get("/api/version")

    assert response.status_code == 200
    assert response.json() == {
        "app_version": version("studio-backend"),
        "api_version": API_VERSION,
    }


def test_openapi_lists_system_operations(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert paths["/api/health"]["get"]["operationId"] == "getHealth"
    assert paths["/api/version"]["get"]["operationId"] == "getVersion"
