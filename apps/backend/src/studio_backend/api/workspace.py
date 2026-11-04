# SPDX-License-Identifier: Apache-2.0
"""Workspace and project routes (TC-35). Error codes: `WorkspaceErrorCode`; statuses: README."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from studio_backend.workspace.models import (
    ArchivedFilter,
    CreateProjectRequest,
    DeletedProject,
    OpenWorkspaceRequest,
    Project,
    ProjectList,
    RecentWorkspaces,
    UpdateProjectRequest,
    Workspace,
)
from studio_backend.workspace.service import WorkspaceService


def get_service(request: Request) -> WorkspaceService:
    service: WorkspaceService = request.app.state.workspace
    return service


Service = Annotated[WorkspaceService, Depends(get_service)]

workspace_router = APIRouter(prefix="/api/workspace", tags=["workspace"])
projects_router = APIRouter(prefix="/api/projects", tags=["projects"])


@workspace_router.get("", operation_id="getWorkspace")
async def get_workspace(service: Service) -> Workspace:
    """The current workspace and its state."""
    return await service.get_workspace()


@workspace_router.post("/open", operation_id="openWorkspace")
async def open_workspace(body: OpenWorkspaceRequest, service: Service) -> Workspace:
    """Open an existing workspace, or initialise a new one in an empty or missing folder.

    Errors: `invalid_workspace_path`, `workspace_not_empty` (a non-empty folder that is not a
    workspace), `workspace_in_use` (another studio has it open), `file_invalid` / `file_too_new`
    (its workspace file). Emits `workspace.changed`.
    """
    return await service.open_workspace(body.path)


@workspace_router.get("/recent", operation_id="getRecentWorkspaces")
async def get_recent_workspaces(service: Service) -> RecentWorkspaces:
    """Workspaces opened before, most recent first."""
    return await service.recent_workspaces()


@projects_router.get("", operation_id="listProjects")
async def list_projects(
    service: Service,
    archived: Annotated[
        ArchivedFilter, Query(description="`false` (default): active only; `true`; `all`.")
    ] = "false",
) -> ProjectList:
    """Projects of the open workspace, including those in the `error` state.

    Errors: `workspace_not_open`.
    """
    return await service.list_projects(archived)


@projects_router.post("", operation_id="createProject")
async def create_project(body: CreateProjectRequest, service: Service) -> Project:
    """Create a project. Errors: `workspace_not_open`, `invalid_project_id`, `project_id_taken`.
    Emits `project.created`."""
    return await service.create_project(body)


@projects_router.get("/{project_id}", operation_id="getProject")
async def get_project(project_id: str, service: Service) -> Project:
    """Errors: `workspace_not_open`, `project_not_found`."""
    return await service.get_project(project_id)


@projects_router.patch("/{project_id}", operation_id="updateProject")
async def update_project(project_id: str, body: UpdateProjectRequest, service: Service) -> Project:
    """Rename (display name only), describe, archive or unarchive. The id never changes.

    Errors: `workspace_not_open`, `project_not_found`, `project_read_only`. Emits
    `project.updated` when something changed.
    """
    return await service.update_project(project_id, body)


@projects_router.delete("/{project_id}", operation_id="deleteProject")
async def delete_project(project_id: str, service: Service) -> DeletedProject:
    """Move the project folder to the trash.

    Errors: `workspace_not_open`, `project_not_found`, `project_read_only`. Emits
    `project.deleted`.
    """
    return await service.delete_project(project_id)
