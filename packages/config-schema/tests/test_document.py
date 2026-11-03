# SPDX-License-Identifier: Apache-2.0
"""TC-32 AC2/AC3: round-trip and canonical serialisation (QA T-32-2, T-32-3)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from studio_config_schema import ProjectFile, dump_bytes, dumps, load, loads, save

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CORPUS = PACKAGE_ROOT / "tests" / "fixtures" / "project" / "v1"
# QA's workspace fixtures (TC-42), read as data. Absent once this package has its own repository.
QA_FIXTURES = PACKAGE_ROOT.parents[1] / "tests" / "fixtures"
QA_WORKSPACES = QA_FIXTURES / "workspaces"


def qa_valid_projects() -> list[Path]:
    if not QA_WORKSPACES.is_dir():
        return []
    found = []
    for path in sorted(QA_WORKSPACES.glob("*/*/project.json")):
        relative = path.relative_to(QA_WORKSPACES)
        workspace, folder = relative.parts[0], relative.parts[1]
        if workspace == "broken" and folder != "valid-project":
            continue  # invalid on purpose: see test_errors.py
        if workspace == "odd-folders" and folder == "My Proj":
            continue  # its id is invalid on purpose (listed as invalid_project_id, TC-36)
        found.append(path)
    found.append(QA_FIXTURES / "edits" / "project-json" / "extra-key.json")
    found.append(QA_FIXTURES / "edits" / "project-json" / "renamed.json")
    return [p for p in found if p.is_file()]


CORPUS_FILES = sorted(CORPUS.glob("*.json"))
QA_FILES = qa_valid_projects()


@pytest.mark.parametrize(
    "path", CORPUS_FILES + QA_FILES, ids=lambda p: p.as_posix().split("fixtures/")[-1]
)
def test_load_save_is_byte_identical(path: Path) -> None:
    original = path.read_bytes()
    assert dump_bytes(load(path, ProjectFile)) == original


def test_qa_fixtures_were_found() -> None:
    if not QA_WORKSPACES.is_dir():
        pytest.skip("QA fixtures not present (package extracted from the monorepo)")
    assert len(QA_FILES) > 250  # many-projects alone has 250


def test_unknown_keys_are_kept() -> None:
    project = load(CORPUS / "full.json", ProjectFile)
    assert project.model_extra == {"userNote": {"z": 1, "a": 2}}
    text = dumps(project)
    assert '"userNote": {\n    "z": 1,\n    "a": 2\n  }' in text


def test_envelope_keys_sorted_but_upstream_order_kept() -> None:
    raw = json.dumps(
        {
            "upstream": {"zeta": 1e-05, "alpha": 0.1, "nested": {"b": 1, "a": 2}},
            "updatedAt": "2026-01-01T00:00:00Z",
            "schemaVersion": 1,
            "name": "N",
            "kind": "project",
            "id": "n",
            "createdAt": "2026-01-01T00:00:00Z",
            "archived": False,
        }
    )
    text = dumps(loads(raw, ProjectFile))
    top_keys = list(json.loads(text))
    assert top_keys == sorted(top_keys)
    assert list(json.loads(text)["upstream"]) == ["zeta", "alpha", "nested"]
    assert '"zeta": 1e-05' in text
    assert '"alpha": 0.1' in text
    assert '"nested": {\n      "b": 1,\n      "a": 2\n    }' in text


def test_canonical_bytes() -> None:
    project = load(CORPUS / "full.json", ProjectFile)
    data = dump_bytes(project)
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in data
    assert b"\\u" not in data
    assert "Équipe ünïcödé".encode() in data
    assert data.endswith(b"}\n")
    assert not data.endswith(b"\n\n")
    assert b'\n  "archived": true,' in data  # 2-space indent


def test_bom_crlf_fraction_and_offset_are_normalised() -> None:
    original = (
        '{\r\n  "kind": "project",\r\n  "schemaVersion": 1,\r\n  "id": "p",\r\n  "name": "P",\r\n'
        '  "createdAt": "2026-01-01T00:00:00.123+00:00",\r\n'
        '  "updatedAt": "2026-01-01T03:00:00+02:00"\r\n}\r\n'
    )
    data = "﻿".encode() + original.encode()
    saved = dump_bytes(loads(data, ProjectFile))
    assert saved == (
        b'{\n  "createdAt": "2026-01-01T00:00:00Z",\n  "id": "p",\n  "kind": "project",\n'
        b'  "name": "P",\n  "schemaVersion": 1,\n  "updatedAt": "2026-01-01T01:00:00Z"\n}\n'
    )


def test_qa_crlf_bom_edit_is_accepted() -> None:
    path = QA_FIXTURES / "edits" / "project-json" / "crlf-bom.json"
    if not path.is_file():
        pytest.skip("QA fixtures not present")
    saved = dump_bytes(load(path, ProjectFile))
    assert saved == path.read_bytes().removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")


def test_absent_optional_fields_stay_absent() -> None:
    text = dumps(load(CORPUS / "minimal.json", ProjectFile))
    assert "description" not in text
    assert "upstream" not in text


def test_new_document_writes_what_was_set() -> None:
    project = ProjectFile(
        schema_version=1,
        kind="project",
        id="new",
        name="New",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        archived=False,
        upstream=None,
    )
    assert json.loads(dumps(project)) == {
        "archived": False,
        "createdAt": "2026-01-01T00:00:00Z",
        "id": "new",
        "kind": "project",
        "name": "New",
        "schemaVersion": 1,
        "updatedAt": "2026-01-01T00:00:00Z",
        "upstream": None,
    }


def test_copy_with_update_writes_the_change() -> None:
    project = load(CORPUS / "minimal.json", ProjectFile)
    renamed = project.model_copy(update={"name": "Renamed", "description": "Now set"})
    saved = json.loads(dumps(renamed))
    assert saved["name"] == "Renamed"
    assert saved["description"] == "Now set"


def test_same_bytes_on_every_os() -> None:
    """The output depends on nothing platform-specific; CI runs this on Windows and Linux."""
    project = load(CORPUS / "full.json", ProjectFile)
    assert dump_bytes(project) == (CORPUS / "full.json").read_bytes()


def test_save_is_atomic_and_canonical(tmp_path: Path) -> None:
    target = tmp_path / "project.json"
    target.write_bytes(b"old content")
    project = load(CORPUS / "full.json", ProjectFile)
    save(target, project)
    assert target.read_bytes() == (CORPUS / "full.json").read_bytes()
    assert [p.name for p in tmp_path.iterdir()] == ["project.json"]  # no temp file left behind
