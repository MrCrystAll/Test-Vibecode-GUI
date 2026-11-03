# SPDX-License-Identifier: Apache-2.0
"""TC-32 AC1: the project file's fields, types and defaults (QA T-32-1)."""

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from studio_config_schema import ErrorReason, ProjectFile, SchemaFileError, loads


def valid(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schemaVersion": 1,
        "kind": "project",
        "id": "my-project",
        "name": "My project",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T01:00:00Z",
    }
    data.update(changes)
    return data


def load_dict(data: dict[str, Any]) -> ProjectFile:
    return loads(json.dumps(data), ProjectFile)


def pointers(exc: SchemaFileError) -> list[str]:
    return [issue.pointer for issue in exc.issues]


def test_minimal_file_and_defaults() -> None:
    project = load_dict(valid())
    assert project.schema_version == 1
    assert project.kind == "project"
    assert project.id == "my-project"
    assert project.name == "My project"
    assert project.description is None
    assert project.archived is False
    assert project.upstream is None
    assert project.created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert project.updated_at == datetime(2026, 1, 1, 1, tzinfo=UTC)


def test_all_fields() -> None:
    project = load_dict(valid(description="d", archived=True, upstream={"ppo": {"lr": 0.0003}}))
    assert project.description == "d"
    assert project.archived is True
    assert project.upstream == {"ppo": {"lr": 0.0003}}


def test_upstream_may_be_null() -> None:
    assert load_dict(valid(upstream=None)).upstream is None


@pytest.mark.parametrize("name", ["x", "x" * 100, "Équipe ünïcödé", "日本語"])
def test_name_length_accepted(name: str) -> None:
    assert load_dict(valid(name=name)).name == name


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_name_length_rejected(name: str) -> None:
    with pytest.raises(SchemaFileError) as caught:
        load_dict(valid(name=name))
    assert caught.value.reason is ErrorReason.INVALID_CONTENT
    assert pointers(caught.value) == ["/name"]


@pytest.mark.parametrize("project_id", ["a", "x" * 64, "project-001", "equipe-7"])
def test_id_accepted(project_id: str) -> None:
    assert load_dict(valid(id=project_id)).id == project_id


@pytest.mark.parametrize("project_id", ["", "x" * 65, "My Proj", "My-Proj", "proj_1", "é", "a/b"])
def test_id_rejected(project_id: str) -> None:
    with pytest.raises(SchemaFileError) as caught:
        load_dict(valid(id=project_id))
    assert pointers(caught.value) == ["/id"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schemaVersion", "1"),
        ("schemaVersion", True),
        ("schemaVersion", 1.0),
        ("schemaVersion", 0),
        ("kind", "workspace"),
        ("archived", "yes"),
        ("archived", 0),
        ("name", 7),
        ("description", 7),
        ("upstream", [1, 2]),
        ("upstream", "text"),
        ("createdAt", 1767225600),
        ("createdAt", "2026-01-01T00:00:00"),
        ("createdAt", "yesterday"),
    ],
)
def test_wrong_types_and_values(field: str, value: object) -> None:
    with pytest.raises(SchemaFileError) as caught:
        load_dict(valid(**{field: value}))
    assert caught.value.reason is ErrorReason.INVALID_CONTENT
    assert pointers(caught.value)[0] == f"/{field}"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-01-01T00:00:00Z", datetime(2026, 1, 1, tzinfo=UTC)),
        ("2026-01-01T00:00:00+00:00", datetime(2026, 1, 1, tzinfo=UTC)),
        ("2026-01-01T00:00:00.987654Z", datetime(2026, 1, 1, tzinfo=UTC)),
        ("2026-01-01T02:00:00+02:00", datetime(2026, 1, 1, tzinfo=UTC)),
    ],
)
def test_timestamps_normalised_to_utc_seconds(text: str, expected: datetime) -> None:
    assert load_dict(valid(createdAt=text)).created_at == expected


def test_python_names_and_aliases_both_construct() -> None:
    made = ProjectFile(
        schema_version=1,
        kind="project",
        id="p",
        name="P",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert made.created_at.tzinfo is UTC
