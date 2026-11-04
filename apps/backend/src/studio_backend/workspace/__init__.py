# SPDX-License-Identifier: Apache-2.0
"""Workspaces on disk (TC-34): layout and id rules, open/initialise, the workspace lock, app
settings.

No HTTP here; the contract story (TC-35) exposes it. Spec: docs/spec/workspace-layout.md.
"""

from studio_backend.workspace.app_settings import (
    SETTINGS_DIR_ENV,
    AppSettingsStore,
    settings_dir,
)
from studio_backend.workspace.errors import (
    InvalidProjectIdError,
    WorkspaceError,
    WorkspaceInUseError,
    WorkspaceInvalidError,
    WorkspaceNotAFolderError,
    WorkspaceNotEmptyError,
)
from studio_backend.workspace.layout import check_project_id, derive_project_id
from studio_backend.workspace.lock import WorkspaceLock
from studio_backend.workspace.workspace import OpenWorkspace, open_workspace

__all__ = [
    "SETTINGS_DIR_ENV",
    "AppSettingsStore",
    "InvalidProjectIdError",
    "OpenWorkspace",
    "WorkspaceError",
    "WorkspaceInUseError",
    "WorkspaceInvalidError",
    "WorkspaceLock",
    "WorkspaceNotAFolderError",
    "WorkspaceNotEmptyError",
    "check_project_id",
    "derive_project_id",
    "open_workspace",
    "settings_dir",
]
