# SPDX-License-Identifier: Apache-2.0
"""`project.json`, the file at the root of every project folder (TC-32 AC1)."""

from typing import ClassVar, Literal

from pydantic import Field, JsonValue

from studio_config_schema.envelope import Envelope, UtcTimestamp

PROJECT_ID_PATTERN = r"^[a-z0-9-]{1,64}$"
"""Characters and length of a project id. Windows reserved names and id derivation are TC-34's."""


class ProjectFile(Envelope):
    """A studio project, stored as `<workspace>/<id>/project.json`.

    Unknown top-level keys are kept on round-trip, so a newer studio's fields and hand-added keys
    survive a save by this studio. `upstream` holds the rlgym-learn configuration verbatim as opaque
    JSON; the studio does not interpret it here.
    """

    KIND: ClassVar[str] = "project"
    SCHEMA_VERSION: ClassVar[int] = 1

    kind: Literal["project"] = Field(description="Always `project`.")
    schema_version: Literal[1] = Field(
        alias="schemaVersion",
        description="Version of the project file format. This schema describes version 1.",
    )
    id: str = Field(
        pattern=PROJECT_ID_PATTERN,
        description=(
            "The project's folder name: lowercase `a-z`, `0-9` and `-`, 1 to 64 characters. "
            "Immutable: renaming a project changes `name` only."
        ),
    )
    name: str = Field(
        min_length=1, max_length=100, description="Display name, 1 to 100 characters."
    )
    description: str | None = Field(default=None, description="Optional free-text description.")
    created_at: UtcTimestamp = Field(
        alias="createdAt", description="Creation time, ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`)."
    )
    updated_at: UtcTimestamp = Field(
        alias="updatedAt", description="Last change, ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`)."
    )
    archived: bool = Field(default=False, description="Archived projects are hidden by default.")
    upstream: dict[str, JsonValue] | None = Field(
        default=None,
        description=(
            "The rlgym-learn configuration, verbatim and opaque to this schema. "
            "Empty (`null` or absent) until 0.3.0."
        ),
    )
