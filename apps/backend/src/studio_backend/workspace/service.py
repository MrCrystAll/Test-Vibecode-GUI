# SPDX-License-Identifier: Apache-2.0
"""What the workspace and project routes need from a workspace implementation (TC-35).

The routes only talk to a `WorkspaceService`. 0.2.0 starts with the in-memory stub (`stub.py`);
the file-system implementation (TC-34/TC-36/TC-37) replaces it in `default_service()` without any
route or contract change. Implementations raise `workspace_error(...)` for every documented error
and publish their events through the `EventHub` they are given.
"""

from typing import Any, Protocol

from studio_backend.errors import ApiError
from studio_backend.workspace.models import (
    ArchivedFilter,
    CreateProjectRequest,
    DeletedProject,
    Project,
    ProjectList,
    RecentWorkspaces,
    UpdateProjectRequest,
    Workspace,
    WorkspaceErrorCode,
)

# HTTP status of each error code. Part of the contract: the README documents it.
STATUS_BY_CODE: dict[WorkspaceErrorCode, int] = {
    "workspace_not_open": 409,
    "workspace_in_use": 409,
    "workspace_not_empty": 409,
    "invalid_workspace_path": 400,
    "project_not_found": 404,
    "project_id_taken": 409,
    "invalid_project_id": 400,
    "project_read_only": 409,
    "file_invalid": 409,
    "file_too_new": 409,
    "migration_failed": 409,
}


def workspace_error(code: WorkspaceErrorCode, message: str, details: Any = None) -> ApiError:
    return ApiError(STATUS_BY_CODE[code], code, message, details)


class WorkspaceService(Protocol):
    async def get_workspace(self) -> Workspace: ...

    async def open_workspace(self, path: str) -> Workspace: ...

    async def recent_workspaces(self) -> RecentWorkspaces: ...

    async def list_projects(self, archived: ArchivedFilter) -> ProjectList: ...

    async def create_project(self, request: CreateProjectRequest) -> Project: ...

    async def get_project(self, project_id: str) -> Project: ...

    async def update_project(self, project_id: str, request: UpdateProjectRequest) -> Project: ...

    async def delete_project(self, project_id: str) -> DeletedProject: ...
