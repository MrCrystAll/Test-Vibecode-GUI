# SPDX-License-Identifier: Apache-2.0
"""Workspace and project routes served by the in-memory stub (TC-35 AC1, AC2, AC4)."""

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from studio_backend import openapi
from studio_backend.workspace.service import STATUS_BY_CODE

WORKSPACE = os.path.abspath(os.path.join(os.sep, "tmp", "Mes projets é"))


def open_workspace(client: TestClient, path: str = WORKSPACE) -> dict[str, Any]:
    response = client.post("/api/workspace/open", json={"path": path})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def create(client: TestClient, **body: Any) -> dict[str, Any]:
    response = client.post("/api/projects", json=body)
    assert response.status_code == 200, response.text
    project: dict[str, Any] = response.json()
    return project


def error_code(response: Any) -> str:
    code: str = response.json()["error"]["code"]
    return code


# --- contract ------------------------------------------------------------------------------------

ROUTES = {
    ("get", "/api/workspace"): ("getWorkspace", "workspace"),
    ("post", "/api/workspace/open"): ("openWorkspace", "workspace"),
    ("get", "/api/workspace/recent"): ("getRecentWorkspaces", "workspace"),
    ("get", "/api/projects"): ("listProjects", "projects"),
    ("post", "/api/projects"): ("createProject", "projects"),
    ("get", "/api/projects/{project_id}"): ("getProject", "projects"),
    ("patch", "/api/projects/{project_id}"): ("updateProject", "projects"),
    ("delete", "/api/projects/{project_id}"): ("deleteProject", "projects"),
}


def test_routes_have_their_operation_ids_and_tags() -> None:
    paths = openapi.build_schema()["paths"]

    for (method, path), (operation_id, tag) in ROUTES.items():
        operation = paths[path][method]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == [tag]


def test_error_codes_are_published_as_an_enum() -> None:
    schemas = openapi.build_schema()["components"]["schemas"]

    codes = set(schemas["WorkspaceErrorCode"]["enum"])

    assert codes == set(STATUS_BY_CODE)
    assert {
        "workspace_not_open",
        "workspace_in_use",
        "workspace_not_empty",
        "project_not_found",
        "project_id_taken",
        "invalid_project_id",
        "file_invalid",
        "file_too_new",
    } <= codes
    assert schemas["ErrorDetail"]["properties"]["code"] == {"title": "Code", "type": "string"}
    assert {"path", "pointer", "issues"} <= set(schemas["FileProblem"]["properties"])


def test_project_responses_reuse_the_project_file_schema() -> None:
    schemas = openapi.build_schema()["components"]["schemas"]

    file_schema = schemas["Project"]["properties"]["file"]

    assert {"$ref": "#/components/schemas/ProjectFile"} in file_schema["anyOf"]
    assert "schemaVersion" in schemas["ProjectFile"]["properties"]


@pytest.mark.parametrize(("method", "path"), sorted(ROUTES))
def test_every_route_needs_the_token(anonymous_client: TestClient, method: str, path: str) -> None:
    response = anonymous_client.request(method, path.replace("{project_id}", "x"), json={})

    assert response.status_code == 401


# --- workspace -----------------------------------------------------------------------------------


def test_no_workspace_at_start(client: TestClient) -> None:
    assert client.get("/api/workspace").json() == {
        "state": "none",
        "path": None,
        "watching": False,
        "problem": None,
    }
    assert client.get("/api/workspace/recent").json() == {"items": []}


def test_open_workspace_and_recent_list(client: TestClient) -> None:
    other = os.path.join(os.path.dirname(WORKSPACE), "other")

    body = open_workspace(client)
    open_workspace(client, other)
    open_workspace(client)

    assert body["state"] == "open"
    assert body["path"] == WORKSPACE
    assert client.get("/api/workspace").json()["path"] == WORKSPACE
    recent = [item["path"] for item in client.get("/api/workspace/recent").json()["items"]]
    assert recent == [WORKSPACE, other]


def test_relative_workspace_path_is_refused(client: TestClient) -> None:
    response = client.post("/api/workspace/open", json={"path": "relative/folder"})

    assert response.status_code == 400
    assert error_code(response) == "invalid_workspace_path"


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/api/projects"), ("post", "/api/projects"), ("get", "/api/projects/a")],
)
def test_project_routes_need_an_open_workspace(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path, json={"name": "A"} if method == "post" else None)

    assert response.status_code == 409
    assert error_code(response) == "workspace_not_open"


# --- projects ------------------------------------------------------------------------------------


def test_create_derives_the_id_from_the_name(client: TestClient) -> None:
    open_workspace(client)

    first = create(client, name="Équipe 7", description="Ma première équipe")
    second = create(client, name="Équipe 7")
    reserved = create(client, name="Con")

    assert first["id"] == "equipe-7"
    assert first["status"] == "ok"
    assert first["path"] == os.path.join(WORKSPACE, "equipe-7")
    assert first["file"]["name"] == "Équipe 7"
    assert first["file"]["description"] == "Ma première équipe"
    assert first["file"]["schemaVersion"] == 1
    assert first["file"]["createdAt"].endswith("Z")
    assert second["id"] == "equipe-7-2"
    assert reserved["id"] == "con-project"


def test_explicit_id_is_used_as_is_or_refused(client: TestClient) -> None:
    open_workspace(client)
    assert create(client, name="Mine", id="my-id")["id"] == "my-id"

    taken = client.post("/api/projects", json={"name": "Other", "id": "my-id"})
    invalid = client.post("/api/projects", json={"name": "Other", "id": "My Proj"})
    reserved = client.post("/api/projects", json={"name": "Other", "id": "nul"})

    assert (taken.status_code, error_code(taken)) == (409, "project_id_taken")
    assert (invalid.status_code, error_code(invalid)) == (400, "invalid_project_id")
    assert "lowercase" in invalid.json()["error"]["message"]
    assert error_code(reserved) == "invalid_project_id"


def test_get_list_and_archive_filter(client: TestClient) -> None:
    open_workspace(client)
    create(client, name="B")
    create(client, name="A")
    archived = client.patch("/api/projects/b", json={"archived": True})

    def ids(query: str) -> list[str]:
        return [item["id"] for item in client.get(f"/api/projects{query}").json()["items"]]

    assert archived.json()["file"]["archived"] is True
    assert ids("") == ["a"]
    assert ids("?archived=false") == ["a"]
    assert ids("?archived=true") == ["b"]
    assert ids("?archived=all") == ["a", "b"]
    assert client.get("/api/projects/a").json()["file"]["name"] == "A"
    assert client.get("/api/projects?archived=maybe").status_code == 422


def test_rename_changes_the_display_name_only(client: TestClient) -> None:
    open_workspace(client)
    create(client, name="Old", description="text")

    renamed = client.patch("/api/projects/old", json={"name": "New name"}).json()
    cleared = client.patch("/api/projects/old", json={"description": None}).json()

    assert renamed["id"] == "old"
    assert renamed["file"]["name"] == "New name"
    assert renamed["file"]["description"] == "text"
    assert cleared["file"]["description"] is None
    assert client.patch("/api/projects/old", json={"id": "new"}).status_code == 422


def test_delete_moves_the_project_away(client: TestClient) -> None:
    open_workspace(client)
    create(client, name="Gone")

    deleted = client.delete("/api/projects/gone")
    again = client.delete("/api/projects/gone")

    assert deleted.json() == {"id": "gone", "trash_path": None}
    assert (again.status_code, error_code(again)) == (404, "project_not_found")
    assert client.get("/api/projects").json() == {"items": []}


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_unknown_project_is_not_found(client: TestClient, method: str) -> None:
    open_workspace(client)

    response = client.request(
        method, "/api/projects/nope", json={"name": "x"} if method == "patch" else None
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "project_not_found",
        "message": "No project with id 'nope'",
        "details": None,
    }
