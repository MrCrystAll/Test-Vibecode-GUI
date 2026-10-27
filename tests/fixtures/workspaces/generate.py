# SPDX-License-Identifier: Apache-2.0
"""Generate the black-box workspace fixtures in this folder (TC-42).

Stdlib only, deterministic: running it twice gives byte-identical files on Windows and Linux.

    uv run --no-project python tests/fixtures/workspaces/generate.py          # rewrite the fixtures
    uv run --no-project python tests/fixtures/workspaces/generate.py --check  # exit 1 if they are stale

The file format follows TC-32 (project envelope) and TC-34 (workspace layout). When those stories change the
format, change the constants below and regenerate; never hand-edit the generated files.
Fixtures are read-only inputs: tests copy a fixture into a temp dir before using it (test strategy §5).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent.parent  # tests/fixtures/

# Format constants (TC-32 / TC-34). Keep in sync with packages/config-schema.
PROJECT_SCHEMA_VERSION = 1
WORKSPACE_SCHEMA_VERSION = 1
TOO_NEW_SCHEMA_VERSION = 999

# Every generated workspace; generate() owns these folders and edits/project-json/, nothing else.
WORKSPACES = (
    "empty",
    "one-project",
    "many-projects",
    "broken",
    "external-edit",
    "odd-folders",
    "not-a-workspace",
)
MANY_PROJECTS_COUNT = 250

BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    """ISO-8601 UTC with a trailing Z, second precision."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dumps(data: Any) -> str:
    """TC-32 AC3 serialisation: UTF-8, LF, 2-space indent, sorted keys, trailing newline."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" so Windows does not turn "\n" into "\r\n".
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)


def write_json(path: Path, data: Any) -> None:
    write_text(path, dumps(data))


def project(
    project_id: str,
    name: str,
    *,
    minutes: int = 0,
    description: str | None = None,
    archived: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created = BASE_TIME + timedelta(minutes=minutes)
    data: dict[str, Any] = {
        "schemaVersion": PROJECT_SCHEMA_VERSION,
        "kind": "project",
        "id": project_id,
        "name": name,
        "createdAt": iso(created),
        "updatedAt": iso(created + timedelta(hours=1)),
        "archived": archived,
        "upstream": None,
    }
    if description is not None:
        data["description"] = description
    if extra:
        data.update(extra)
    return data


def init_workspace(root: Path) -> None:
    write_json(root / ".studio" / "workspace.json", {"schemaVersion": WORKSPACE_SCHEMA_VERSION, "kind": "workspace"})


def add_project(root: Path, data: dict[str, Any]) -> None:
    write_json(root / data["id"] / "project.json", data)


def build_empty(root: Path) -> None:
    """An initialised workspace with no projects."""
    init_workspace(root)


def build_one_project(root: Path) -> None:
    init_workspace(root)
    add_project(root, project("first-project", "First project", description="Created by the QA fixture generator."))


def build_many_projects(root: Path) -> None:
    """MANY_PROJECTS_COUNT valid projects with a deterministic mix of the interesting shapes."""
    init_workspace(root)
    for i in range(MANY_PROJECTS_COUNT):
        n = i + 1
        project_id = f"project-{n:03d}"
        name = f"Project {n:03d}"
        description: str | None = None
        extra: dict[str, Any] | None = None
        if n % 7 == 0:
            name = f"Équipe ünïcödé {n:03d}"  # non-ASCII display name
        if n % 11 == 0:
            name = ("Long name " + "x" * 100)[:100]  # max length (TC-32 AC1: 1-100 chars)
        if n % 3 == 0:
            description = f"Description of project {n:03d}."
        if n % 50 == 0:
            extra = {"userNote": f"hand-added key {n:03d}"}  # unknown top-level key (TC-32 AC2)
        # Updated order differs from id order so "sorted by last updated" is observable (TC-39 AC1).
        minutes = (n * 37) % (MANY_PROJECTS_COUNT * 2)
        add_project(
            root,
            project(project_id, name, minutes=minutes, description=description, archived=n % 10 == 0, extra=extra),
        )


def build_broken(root: Path) -> None:
    """One valid project next to every kind of bad project file (TC-36 AC3, TC-39 AC3)."""
    init_workspace(root)
    add_project(root, project("valid-project", "Valid project"))
    write_text(root / "invalid-json" / "project.json", '{\n  "kind": "project",\n  "name": "Missing brace"\n')
    missing = project("missing-name", "unused")
    del missing["name"]
    add_project(root, missing)
    add_project(root, project("wrong-type", "Wrong type", extra={"archived": "yes", "schemaVersion": "1"}))
    add_project(
        root,
        project("too-new", "Written by a newer studio", extra={"schemaVersion": TOO_NEW_SCHEMA_VERSION, "newField": {}}),
    )
    write_text(root / "empty-file" / "project.json", "")
    write_text(root / "not-an-object" / "project.json", "[]\n")


def build_external_edit(root: Path) -> None:
    """Start state for the hand-edit tests; the edits to apply are in ../edits/project-json/ (TC-36 AC4, TC-37)."""
    init_workspace(root)
    add_project(root, project("edit-me", "Edit me", description="Original description."))
    add_project(root, project("bystander", "Bystander"))


def build_odd_folders(root: Path) -> None:
    """Folders that are not plain projects; listing rules decided by the PO in TC-42 (Q3)."""
    init_workspace(root)
    add_project(root, project("valid-project", "Valid project"))
    # Invalid folder name (uppercase + space): listed read-only with invalid_project_id.
    write_json(root / "My Proj" / "project.json", project("My Proj", "Hand-made folder"))
    # No project.json: ignored.
    write_text(root / "no-project-file" / "notes.txt", "Not a project.\n")
    # Dot-folder: ignored, even with a project.json inside.
    write_json(root / ".hidden-project" / "project.json", project("hidden-project", "Hidden"))
    # id field differs from the folder: the folder name wins, file_invalid with pointer /id.
    write_json(root / "id-mismatch" / "project.json", project("other-id", "Id mismatch"))


def build_not_a_workspace(root: Path) -> None:
    """A non-empty folder without .studio/workspace.json: opening it must fail with workspace_not_empty (TC-34 AC3)."""
    write_text(root / "notes.txt", "Someone's documents. The studio must not write here.\n")


def build_edits(root: Path) -> None:
    """Replacement files for external-edit/edit-me/project.json, one per hand-edit case (docs/qa/manual/workspace.md M-ED)."""
    base = project("edit-me", "Edit me", description="Original description.")
    renamed = dict(base, name="Edited by hand", description="Edited in a text editor.")
    write_json(root / "renamed.json", renamed)
    write_json(root / "extra-key.json", dict(base, userNote="added by hand, must survive an app rename"))
    write_json(root / "too-new.json", dict(base, schemaVersion=TOO_NEW_SCHEMA_VERSION, newField={"x": 1}))
    write_text(root / "invalid-json.json", dumps(base)[:-2] + "\n")  # drops the closing brace
    # What old Windows Notepad writes: UTF-8 BOM and CRLF. Kept as bytes by tests/fixtures/.gitattributes.
    write_text(root / "crlf-bom.json", "﻿" + dumps(renamed).replace("\n", "\r\n"))


BUILDERS = {
    "empty": build_empty,
    "one-project": build_one_project,
    "many-projects": build_many_projects,
    "broken": build_broken,
    "external-edit": build_external_edit,
    "odd-folders": build_odd_folders,
    "not-a-workspace": build_not_a_workspace,
}


# Output folders relative to tests/fixtures/, each rebuilt from scratch by its builder.
OUTPUTS = {f"workspaces/{name}": BUILDERS[name] for name in WORKSPACES} | {"edits/project-json": build_edits}


def generate(fixtures_root: Path) -> None:
    for rel, build in OUTPUTS.items():
        out = fixtures_root / rel
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        build(out)


def snapshot(fixtures_root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for rel in OUTPUTS:
        base = fixtures_root / rel
        if base.exists():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    files[p.relative_to(fixtures_root).as_posix()] = p.read_bytes()
    return files


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="compare with the committed fixtures, write nothing")
    args = parser.parse_args(argv)

    if not args.check:
        generate(FIXTURES)
        print(f"generated {len(snapshot(FIXTURES))} files under {FIXTURES}")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        generate(Path(tmp))
        expected, actual = snapshot(Path(tmp)), snapshot(FIXTURES)
    stale = sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))
    if stale:
        print("workspace fixtures are stale; run tests/fixtures/workspaces/generate.py and commit:", file=sys.stderr)
        for k in stale[:20]:
            print(f"  {k}", file=sys.stderr)
        return 1
    print(f"workspace fixtures up to date ({len(actual)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
