# SPDX-License-Identifier: Apache-2.0
"""A synthetic, test-only file type with a v0 -> v1 migration (TC-33 AC6).

No real v0 project format exists, so this kind proves the mechanism. It is never registered in the
shipped package: the backend has no test-only migration path (PO decision, Q1 on TC-42).
"""

from typing import Any, ClassVar, Literal

from pydantic import Field

from studio_config_schema import Envelope, Migrations

SAMPLE_MIGRATIONS = Migrations("sample", current=1)


@SAMPLE_MIGRATIONS.step(0)
def _v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """v0 had `title` and comma-separated `tags`; v1 has `name` and a list of tags."""
    data["name"] = data.pop("title")
    data["tags"] = [tag.strip() for tag in data.get("tags", "").split(",") if tag.strip()]
    return data


SAMPLE_MIGRATIONS.seal()


class SampleFile(Envelope):
    KIND: ClassVar[str] = "sample"
    SCHEMA_VERSION: ClassVar[int] = 1
    MIGRATIONS: ClassVar[Migrations] = SAMPLE_MIGRATIONS

    kind: Literal["sample"]
    schema_version: Literal[1] = Field(alias="schemaVersion")
    name: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
