# SPDX-License-Identifier: Apache-2.0
"""The workspace marker and the app settings file (TC-34).

- `<workspace>/.studio/workspace.json` marks a folder as a studio workspace (`WorkspaceMarker`).
- The app settings file in the OS user config dir remembers the current workspace and the recently
  opened ones (`AppSettings`). Only the backend reads or writes it (ADR-0002).

The folder layout around these files is specified in `docs/spec/workspace-layout.md`.
"""

from typing import ClassVar, Literal

from pydantic import Field

from studio_config_schema.envelope import Envelope
from studio_config_schema.migrations import Migrations

WORKSPACE_MIGRATIONS = Migrations("workspace", current=1).seal()
"""v1 is the first workspace marker format: no steps yet."""

APP_SETTINGS_MIGRATIONS = Migrations("app-settings", current=1).seal()
"""v1 is the first app settings format: no steps yet."""

MAX_RECENT_WORKSPACES = 10
"""How many recently opened workspaces the app settings keep (most recent first)."""


class WorkspaceMarker(Envelope):
    """`<workspace>/.studio/workspace.json`: its presence makes a folder a studio workspace.

    v1 carries only the envelope. Unknown keys are kept, like in every studio file.
    """

    KIND: ClassVar[str] = "workspace"
    SCHEMA_VERSION: ClassVar[int] = 1
    MIGRATIONS: ClassVar[Migrations] = WORKSPACE_MIGRATIONS

    kind: Literal["workspace"] = Field(description="Always `workspace`.")
    schema_version: Literal[1] = Field(
        alias="schemaVersion",
        description="Version of the workspace marker format. This schema describes version 1.",
    )


class AppSettings(Envelope):
    """The studio's own settings, in the OS user config dir (`settings.json`).

    Paths are absolute, as the user's OS spells them. They are remembered, not trusted: opening one
    goes through the same checks as a path the user just picked.
    """

    KIND: ClassVar[str] = "app-settings"
    SCHEMA_VERSION: ClassVar[int] = 1
    MIGRATIONS: ClassVar[Migrations] = APP_SETTINGS_MIGRATIONS

    kind: Literal["app-settings"] = Field(description="Always `app-settings`.")
    schema_version: Literal[1] = Field(
        alias="schemaVersion",
        description="Version of the app settings format. This schema describes version 1.",
    )
    current_workspace: str | None = Field(
        default=None,
        alias="currentWorkspace",
        min_length=1,
        description="Absolute path of the workspace opened last, or null before the first one.",
    )
    recent_workspaces: list[str] = Field(
        default_factory=list,
        alias="recentWorkspaces",
        max_length=MAX_RECENT_WORKSPACES,
        description=(
            f"Absolute paths of recently opened workspaces, most recent first, at most "
            f"{MAX_RECENT_WORKSPACES}, without duplicates."
        ),
    )
