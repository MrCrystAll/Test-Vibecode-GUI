# SPDX-License-Identifier: Apache-2.0
"""TC-32 AC4: the published JSON Schema (QA T-32-4, X2-4)."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from studio_config_schema import generate

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = PACKAGE_ROOT / "schemas" / "project.v1.schema.json"
CORPUS = PACKAGE_ROOT / "tests" / "fixtures" / "project" / "v1"
QA_WORKSPACES = PACKAGE_ROOT.parents[1] / "tests" / "fixtures" / "workspaces"


def schema() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    return data


def test_committed_schemas_are_up_to_date() -> None:
    stale = generate.stale_files()
    assert not stale, f"Stale JSON Schema(s) {stale}. Run: {generate.COMMAND}"


def test_check_reports_drift_with_the_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generate.write(tmp_path)
    assert generate.main(["--check", "--out", str(tmp_path)]) == 0
    target = tmp_path / "project.v1.schema.json"
    target.write_text(
        target.read_text(encoding="utf-8").replace("Display name", "Name"), encoding="utf-8"
    )
    assert generate.main(["--check", "--out", str(tmp_path)]) == 1
    assert generate.COMMAND in capsys.readouterr().err


def test_schema_header() -> None:
    data = schema()
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert data["$id"].endswith("/packages/config-schema/schemas/project.v1.schema.json")
    Draft202012Validator.check_schema(data)


def test_written_with_lf_and_trailing_newline() -> None:
    raw = SCHEMA_FILE.read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"}\n")


def valid_samples() -> list[Path]:
    paths = sorted(CORPUS.glob("*.json"))
    if QA_WORKSPACES.is_dir():
        for path in sorted(QA_WORKSPACES.glob("*/*/project.json")):
            workspace, folder = path.relative_to(QA_WORKSPACES).parts[:2]
            if (workspace == "broken" and folder != "valid-project") or folder == "My Proj":
                continue
            paths.append(path)
    return paths


@pytest.mark.parametrize("path", valid_samples(), ids=lambda p: p.parent.name + "/" + p.name)
def test_valid_files_validate(path: Path) -> None:
    Draft202012Validator(schema()).validate(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("folder", ["missing-name", "not-an-object", "too-new", "wrong-type"])
def test_broken_files_fail(folder: str) -> None:
    path = QA_WORKSPACES / "broken" / folder / "project.json"
    if not path.is_file():
        pytest.skip("QA fixtures not present")
    validator = Draft202012Validator(schema())
    assert not validator.is_valid(json.loads(path.read_text(encoding="utf-8")))
