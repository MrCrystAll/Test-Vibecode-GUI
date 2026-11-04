# SPDX-License-Identifier: Apache-2.0
"""Errors of the workspace module (TC-34). Each has a stable `code` that the API maps (TC-35)."""

from pathlib import Path


class WorkspaceError(Exception):
    """Base of every workspace failure. `code` is stable; `message` is for people and logs."""

    code = "workspace_error"

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


class WorkspaceNotEmptyError(WorkspaceError):
    """A non-empty folder without `.studio/workspace.json`: refused, nothing written (AC3)."""

    code = "workspace_not_empty"


class WorkspaceNotAFolderError(WorkspaceError):
    """The path exists but is a file (or something else that is not a folder)."""

    code = "workspace_not_a_folder"


class WorkspaceInvalidError(WorkspaceError):
    """`.studio/workspace.json` exists but cannot be read: bad JSON, wrong content, too new.

    `reason` is the `studio_config_schema.ErrorReason` value (`invalid_json`, `too_new`, ...).
    """

    code = "workspace_invalid"

    def __init__(self, path: Path, message: str, reason: str) -> None:
        super().__init__(path, message)
        self.reason = reason


class WorkspaceInUseError(WorkspaceError):
    """Another backend holds `.studio/lock` (AC4)."""

    code = "workspace_in_use"


class InvalidProjectIdError(ValueError):
    """An explicit project id breaks a slug rule. `rule` names it (PO Q3 on TC-42)."""

    code = "invalid_project_id"

    def __init__(self, project_id: str, rule: str) -> None:
        self.project_id = project_id
        self.rule = rule
        super().__init__(f"invalid project id {project_id!r}: {rule}")
