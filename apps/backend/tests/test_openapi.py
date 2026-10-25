# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from studio_backend import openapi
from studio_backend.version import API_VERSION


def test_render_is_deterministic_and_lf_terminated() -> None:
    first = openapi.render(openapi.build_schema())
    second = openapi.render(openapi.build_schema())

    assert first == second
    assert first.endswith("}\n")
    assert "\r" not in first


def test_render_sorts_keys() -> None:
    assert openapi.render({"b": 1, "a": {"d": 2, "c": 3}}) == (
        '{\n  "a": {\n    "c": 3,\n    "d": 2\n  },\n  "b": 1\n}\n'
    )


def test_schema_version_is_the_contract_version() -> None:
    assert openapi.build_schema()["info"]["version"] == API_VERSION


def test_every_operation_is_named_tagged_and_typed() -> None:
    operations = [
        (path, method, operation)
        for path, item in openapi.build_schema()["paths"].items()
        for method, operation in item.items()
    ]
    assert operations

    for path, method, operation in operations:
        where = f"{method.upper()} {path}"
        assert operation.get("operationId"), f"{where}: missing operationId"
        assert operation.get("tags"), f"{where}: missing tags"
        ok = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert "$ref" in ok, f"{where}: 200 response has no response model"
        error = operation["responses"]["default"]["content"]["application/json"]["schema"]
        assert error == {"$ref": "#/components/schemas/ErrorResponse"}, where


def test_operation_ids_are_unique() -> None:
    ids = [
        operation["operationId"]
        for item in openapi.build_schema()["paths"].values()
        for operation in item.values()
    ]

    assert len(ids) == len(set(ids))


def test_export_writes_the_file_and_check_accepts_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "openapi.json"

    assert openapi.main(["--output", str(output)]) == 0
    assert output.read_bytes() == openapi.render(openapi.build_schema()).encode("utf-8")
    assert openapi.main(["--output", str(output), "--check"]) == 0
    assert "up to date" in capsys.readouterr().out


def test_check_fails_when_the_file_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "openapi.json"

    assert openapi.main(["--output", str(output), "--check"]) == 1
    assert "export-openapi" in capsys.readouterr().err
    assert not output.exists()


def test_check_fails_and_writes_nothing_when_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "openapi.json"
    output.write_text("{}\n", encoding="utf-8")

    assert openapi.main(["--output", str(output), "--check"]) == 1
    assert "export-openapi" in capsys.readouterr().err
    assert output.read_text(encoding="utf-8") == "{}\n"


def test_default_output_is_found_from_a_subfolder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "packages" / "contract").mkdir(parents=True)
    subfolder = tmp_path / "apps" / "backend"
    subfolder.mkdir(parents=True)
    monkeypatch.chdir(subfolder)

    assert openapi.main([]) == 0
    assert (tmp_path / "packages" / "contract" / "openapi.json").is_file()


def test_default_output_needs_a_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit, match="packages/contract/ not found"):
        openapi.main([])


def test_committed_contract_is_up_to_date() -> None:
    # Same check as the CI hook, so a stale contract also fails `pytest` locally.
    committed = Path(__file__).resolve().parents[3] / openapi.CONTRACT_FILE
    if not committed.is_file():
        pytest.skip("not in the monorepo (apps/backend extracted)")

    assert committed.read_text(encoding="utf-8") == openapi.render(openapi.build_schema()), (
        "packages/contract/openapi.json is stale: "
        "run `uv run --package studio-backend export-openapi`"
    )
