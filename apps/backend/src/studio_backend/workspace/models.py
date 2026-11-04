# SPDX-License-Identifier: Apache-2.0
"""HTTP models of the workspace and project API (TC-35, frozen for 0.2.0).

Top-level fields are snake_case like the rest of the API. A project's `file` is the TC-32
`ProjectFile` itself, so it keeps the file's own camelCase keys (`schemaVersion`, `createdAt`).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from studio_config_schema import ProjectFile

WorkspaceErrorCode = Literal[
    "workspace_not_open",
    "workspace_in_use",
    "workspace_not_empty",
    "invalid_workspace_path",
    "project_not_found",
    "project_id_taken",
    "invalid_project_id",
    "project_read_only",
    "file_invalid",
    "file_too_new",
    "migration_failed",
]
"""Error codes of the workspace and project routes (`ErrorDetail.code`, and `Problem.code`).

`ErrorDetail.code` stays a string: these come on top of the generic codes (`not_found`,
`validation_error`, ...). Clients show a generic message for a code they don't know.
"""


class FileIssue(BaseModel):
    pointer: str = Field(description='RFC 6901 JSON pointer; `""` is the whole document.')
    message: str


class FileProblem(BaseModel):
    """Where a file is broken. `details` of a `file_invalid`, `file_too_new` or
    `migration_failed` error, and `Problem.file`."""

    path: str = Field(description="Absolute path of the file.")
    pointer: str = Field(description="Pointer of the first issue.")
    issues: list[FileIssue] = Field(description="Every issue found, at least one.")


class Problem(BaseModel):
    """Why a workspace or project is in the `error` state."""

    code: WorkspaceErrorCode
    message: str
    file: FileProblem | None = None


# --- workspace -----------------------------------------------------------------------------------


class Workspace(BaseModel):
    """The workspace the backend works in. At most one is open at a time."""

    state: Literal["none", "open", "error"] = Field(
        description="`none`: nothing opened yet. `open`: ready. `error`: see `problem`."
    )
    path: str | None = Field(description="Absolute path; `null` in the `none` state.")
    watching: bool = Field(
        description="Whether external edits are seen live. `false`: the UI should offer a refresh."
    )
    problem: Problem | None = Field(default=None, description="Set in the `error` state only.")


class OpenWorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        min_length=1,
        description=(
            "Absolute folder path. An existing workspace is opened; an empty or missing folder "
            "is initialised as a new workspace."
        ),
    )


class RecentWorkspace(BaseModel):
    path: str
    opened_at: datetime = Field(description="Last time it was opened, ISO-8601 UTC.")


class RecentWorkspaces(BaseModel):
    items: list[RecentWorkspace] = Field(description="Most recent first.")


# --- projects ------------------------------------------------------------------------------------


class Project(BaseModel):
    """One project folder of the workspace.

    `status: "error"` projects are listed so the user can see and fix them, but they are read-only:
    `PATCH` and `DELETE` answer `project_read_only`.
    """

    id: str = Field(description="The folder name. Immutable.")
    path: str = Field(description="Absolute path of the project folder.")
    status: Literal["ok", "error"]
    file: ProjectFile | None = Field(
        description="The parsed `project.json` (TC-32 schema); `null` when it can't be read."
    )
    problem: Problem | None = Field(default=None, description="Set when `status` is `error`.")


class ProjectList(BaseModel):
    items: list[Project] = Field(description="Sorted by id.")


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100, description="Display name.")
    id: str | None = Field(
        default=None,
        description=(
            "Folder name. Omitted: derived from `name` and never taken. Given: used as is, or "
            "refused with `invalid_project_id` / `project_id_taken`."
        ),
    )
    description: str | None = None


class UpdateProjectRequest(BaseModel):
    """Only the fields sent change. `description: null` clears it. The id never changes."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    archived: bool | None = None


class DeletedProject(BaseModel):
    id: str
    trash_path: str | None = Field(
        description="Where the folder went, when the backend knows it (OS trash: `null`)."
    )


ArchivedFilter = Literal["false", "true", "all"]
