# SPDX-License-Identifier: Apache-2.0
"""TC-32 AC5: one error type, with path, JSON pointer and message (QA T-32-5)."""

import json
from pathlib import Path

import pytest

from studio_config_schema import ErrorReason, ProjectFile, SchemaFileError, load, loads
from studio_config_schema.errors import Issue, json_pointer

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
QA_FIXTURES = PACKAGE_ROOT.parents[1] / "tests" / "fixtures"

VALID = {
    "schemaVersion": 1,
    "kind": "project",
    "id": "p",
    "name": "P",
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:00Z",
}


def refused(data: bytes | str, path: Path | None = None) -> SchemaFileError:
    with pytest.raises(SchemaFileError) as caught:
        loads(data, ProjectFile, path=path)
    return caught.value


@pytest.mark.parametrize(
    ("data", "reason", "pointer", "words"),
    [
        (b"", ErrorReason.INVALID_JSON, "", "empty"),
        (b"  \n", ErrorReason.INVALID_JSON, "", "empty"),
        (b'{"kind": "project",', ErrorReason.INVALID_JSON, "", "line 1"),
        (b"\xff\xfe{}", ErrorReason.INVALID_JSON, "", "UTF-8"),
        (b'{"x": NaN}', ErrorReason.INVALID_JSON, "", "NaN"),
        (b"[]", ErrorReason.INVALID_CONTENT, "", "an array"),
        (b'"text"', ErrorReason.INVALID_CONTENT, "", "a string"),
        (b"null", ErrorReason.INVALID_CONTENT, "", "null"),
    ],
)
def test_not_a_document(data: bytes, reason: ErrorReason, pointer: str, words: str) -> None:
    error = refused(data)
    assert error.reason is reason
    assert error.pointer == pointer
    assert words in error.message


@pytest.mark.parametrize("field", sorted(VALID))
def test_missing_required_field(field: str) -> None:
    data = {k: v for k, v in VALID.items() if k != field}
    error = refused(json.dumps(data))
    assert error.reason is ErrorReason.INVALID_CONTENT
    assert error.pointer == f"/{field}"
    assert error.message == "required field is missing"


def test_every_issue_is_reported() -> None:
    error = refused(json.dumps({**VALID, "archived": "yes", "schemaVersion": "1"}))
    assert sorted(i.pointer for i in error.issues) == ["/archived", "/schemaVersion"]


def test_upstream_content_is_opaque() -> None:
    project = loads(json.dumps({**VALID, "upstream": {"a": [{"b": None}]}}), ProjectFile)
    assert project.upstream == {"a": [{"b": None}]}


@pytest.mark.parametrize("version", [2, 999])
def test_too_new(version: int) -> None:
    error = refused(json.dumps({**VALID, "schemaVersion": version}))
    assert error.reason is ErrorReason.TOO_NEW
    assert error.pointer == "/schemaVersion"
    assert "newer studio" in error.message


def test_error_carries_the_path(tmp_path: Path) -> None:
    target = tmp_path / "project.json"
    target.write_bytes(b"{")
    with pytest.raises(SchemaFileError) as caught:
        load(target, ProjectFile)
    assert caught.value.path == target
    assert str(target) in str(caught.value)


def test_missing_file_is_an_os_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "absent.json", ProjectFile)


def test_needs_an_issue() -> None:
    with pytest.raises(ValueError, match="at least one issue"):
        SchemaFileError(None, ErrorReason.INVALID_JSON, [])


def test_str_lists_every_issue() -> None:
    error = SchemaFileError(
        Path("p.json"), ErrorReason.INVALID_CONTENT, [Issue("", "a"), Issue("/x", "b")]
    )
    assert str(error) == "p.json: /: a; /x: b"


@pytest.mark.parametrize(
    ("location", "pointer"),
    [((), ""), (("a",), "/a"), (("a/b", 0), "/a~1b/0"), (("m~n",), "/m~0n")],
)
def test_json_pointer(location: tuple[int | str, ...], pointer: str) -> None:
    assert json_pointer(location) == pointer


QA_BROKEN = {
    "empty-file": (ErrorReason.INVALID_JSON, ""),
    "invalid-json": (ErrorReason.INVALID_JSON, ""),
    "missing-name": (ErrorReason.INVALID_CONTENT, "/name"),
    "not-an-object": (ErrorReason.INVALID_CONTENT, ""),
    "too-new": (ErrorReason.TOO_NEW, "/schemaVersion"),
    "wrong-type": (ErrorReason.INVALID_CONTENT, "/archived"),
}


@pytest.mark.parametrize("folder", sorted(QA_BROKEN))
def test_qa_broken_fixtures(folder: str) -> None:
    path = QA_FIXTURES / "workspaces" / "broken" / folder / "project.json"
    if not path.is_file():
        pytest.skip("QA fixtures not present")
    with pytest.raises(SchemaFileError) as caught:
        load(path, ProjectFile)
    reason, pointer = QA_BROKEN[folder]
    assert caught.value.reason is reason
    assert pointer in [i.pointer for i in caught.value.issues]
    assert caught.value.path == path
    assert caught.value.message


@pytest.mark.parametrize(
    ("name", "reason"),
    [("invalid-json.json", ErrorReason.INVALID_JSON), ("too-new.json", ErrorReason.TOO_NEW)],
)
def test_qa_edit_fixtures(name: str, reason: ErrorReason) -> None:
    path = QA_FIXTURES / "edits" / "project-json" / name
    if not path.is_file():
        pytest.skip("QA fixtures not present")
    with pytest.raises(SchemaFileError) as caught:
        load(path, ProjectFile)
    assert caught.value.reason is reason
