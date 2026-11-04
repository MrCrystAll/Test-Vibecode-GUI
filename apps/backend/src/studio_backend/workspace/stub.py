# SPDX-License-Identifier: Apache-2.0
"""In-memory `WorkspaceService` (TC-35 AC4): the contract's semantics without any file system.

It lets track B build the screens against real routes and events before the file-system
implementation lands. Nothing is read from or written to disk; state is lost on restart. It follows
the documented happy path, `project_not_found`, `project_id_taken`, `invalid_project_id` and
`workspace_not_open`. Every change it makes is announced on the `workspace` topic with
`source: "app"`.
"""

import os
from datetime import UTC, datetime
from typing import Any

from studio_config_schema import ProjectFile, derive_project_id, is_taken, project_id_problem

from studio_backend.events import (
    ProjectEventPayload,
    WorkspaceChangedPayload,
    WsProjectCreated,
    WsProjectDeleted,
    WsProjectUpdated,
    WsWorkspaceChanged,
)
from studio_backend.hub import EventHub
from studio_backend.workspace.models import (
    ArchivedFilter,
    CreateProjectRequest,
    DeletedProject,
    Project,
    ProjectList,
    RecentWorkspace,
    RecentWorkspaces,
    UpdateProjectRequest,
    Workspace,
)
from studio_backend.workspace.service import workspace_error

MAX_RECENT = 10


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class InMemoryWorkspaceService:
    def __init__(self, hub: EventHub) -> None:
        self._hub = hub
        self._path: str | None = None
        self._projects: dict[str, ProjectFile] = {}
        self._recent: list[RecentWorkspace] = []

    # --- workspace -------------------------------------------------------------------------------

    async def get_workspace(self) -> Workspace:
        if self._path is None:
            return Workspace(state="none", path=None, watching=False)
        return Workspace(state="open", path=self._path, watching=False)

    async def open_workspace(self, path: str) -> Workspace:
        if not os.path.isabs(path):
            raise workspace_error("invalid_workspace_path", f"Not an absolute path: {path!r}")
        normalized = os.path.normpath(path)
        if normalized != self._path:
            self._path = normalized
            self._projects = {}
        self._recent = [item for item in self._recent if item.path != normalized]
        self._recent.insert(0, RecentWorkspace(path=normalized, opened_at=_now()))
        del self._recent[MAX_RECENT:]
        await self._hub.publish(
            "workspace",
            WsWorkspaceChanged(payload=WorkspaceChangedPayload(path=normalized, source="app")),
        )
        return await self.get_workspace()

    async def recent_workspaces(self) -> RecentWorkspaces:
        return RecentWorkspaces(items=list(self._recent))

    # --- projects --------------------------------------------------------------------------------

    async def list_projects(self, archived: ArchivedFilter) -> ProjectList:
        self._workspace_path()
        files = [self._projects[key] for key in sorted(self._projects)]
        if archived != "all":
            files = [file for file in files if file.archived == (archived == "true")]
        return ProjectList(items=[self._project(file) for file in files])

    async def create_project(self, request: CreateProjectRequest) -> Project:
        self._workspace_path()
        if request.id is None:
            project_id = derive_project_id(request.name, self._projects)
        else:
            project_id = request.id
            problem = project_id_problem(project_id)
            if problem is not None:
                raise workspace_error(
                    "invalid_project_id", f"Invalid project id {project_id!r}: {problem}"
                )
            if is_taken(project_id, self._projects):
                raise workspace_error(
                    "project_id_taken", f"A project with id {project_id!r} already exists"
                )
        now = _now()
        file = ProjectFile(
            kind="project",
            schemaVersion=1,
            id=project_id,
            name=request.name,
            description=request.description,
            createdAt=now,
            updatedAt=now,
        )
        self._projects[project_id] = file
        await self._announce(WsProjectCreated, project_id)
        return self._project(file)

    async def get_project(self, project_id: str) -> Project:
        return self._project(self._file(project_id))

    async def update_project(self, project_id: str, request: UpdateProjectRequest) -> Project:
        file = self._file(project_id)
        changes: dict[str, Any] = {
            key: value
            for key, value in request.model_dump(exclude_unset=True).items()
            if value is not None or key == "description"
        }
        if changes:
            data = file.model_dump(by_alias=True) | changes | {"updatedAt": _now()}
            file = ProjectFile.model_validate(data)
            self._projects[project_id] = file
            await self._announce(WsProjectUpdated, project_id)
        return self._project(file)

    async def delete_project(self, project_id: str) -> DeletedProject:
        self._file(project_id)
        del self._projects[project_id]
        await self._announce(WsProjectDeleted, project_id)
        return DeletedProject(id=project_id, trash_path=None)

    # --- helpers ---------------------------------------------------------------------------------

    def _workspace_path(self) -> str:
        if self._path is None:
            raise workspace_error("workspace_not_open", "No workspace is open")
        return self._path

    def _file(self, project_id: str) -> ProjectFile:
        self._workspace_path()
        file = self._projects.get(project_id)
        if file is None:
            raise workspace_error("project_not_found", f"No project with id {project_id!r}")
        return file

    def _project(self, file: ProjectFile) -> Project:
        return Project(
            id=file.id,
            path=os.path.join(self._workspace_path(), file.id),
            status="ok",
            file=file,
        )

    async def _announce(
        self, event: type[WsProjectCreated | WsProjectUpdated | WsProjectDeleted], project_id: str
    ) -> None:
        payload = ProjectEventPayload(project_id=project_id, source="app")
        await self._hub.publish("workspace", event(payload=payload))
