# SPDX-License-Identifier: Apache-2.0
"""TC-33: migration chain, in-memory migration, upgrade with backup (QA T-33-1..7)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sample_kind import SAMPLE_MIGRATIONS, SampleFile

from studio_config_schema import (
    BACKUP_DIR,
    AppSettings,
    Envelope,
    ErrorReason,
    MigrationChainError,
    Migrations,
    MigrationStepError,
    ProjectFile,
    SchemaFileError,
    WorkspaceMarker,
    load,
    read,
    upgrade,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CORPUS = PACKAGE_ROOT / "tests" / "fixtures"
MODELS: dict[str, type[Envelope]] = {
    "project": ProjectFile,
    "sample": SampleFile,
    "workspace": WorkspaceMarker,
    "app-settings": AppSettings,
}
"""Every kind in the corpus. A new corpus folder without a model here fails test_corpus_layout."""
NOW = datetime(2026, 11, 4, 17, 45, 0, tzinfo=UTC)
V0 = (CORPUS / "sample" / "v0" / "basic.json").read_bytes()


@pytest.fixture
def hostile_dir(tmp_path: Path) -> Path:
    """A folder whose path has a space and a non-ASCII character (T-33-7)."""
    folder = tmp_path / "studio wörk é"
    folder.mkdir()
    return folder


def write(folder: Path, data: bytes | dict[str, Any], name: str = "sample.json") -> Path:
    target = folder / name
    target.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode())
    return target


def snapshot(folder: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(p.relative_to(folder)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


# AC1: the chain -------------------------------------------------------------------------------


def identity(data: dict[str, Any]) -> dict[str, Any]:
    return data


def test_duplicate_step_fails_when_declared() -> None:
    chain = Migrations("x", current=3)
    chain.step(1)(identity)
    with pytest.raises(MigrationChainError, match="duplicate step v1 -> v2"):
        chain.step(1)(identity)


def test_gap_fails_at_seal() -> None:
    chain = Migrations("x", current=4)
    chain.step(1)(identity)
    chain.step(3)(identity)
    with pytest.raises(MigrationChainError, match=r"gap .* missing v2 -> v3"):
        chain.seal()


@pytest.mark.parametrize("last", [1, 3])
def test_chain_must_end_at_current(last: int) -> None:
    chain = Migrations("x", current=3)
    chain.step(last)(identity)
    with pytest.raises(MigrationChainError, match="last step must be v2 -> v3"):
        chain.seal()


def test_empty_chain_reads_only_current() -> None:
    chain = Migrations("x", current=1).seal()
    assert chain.oldest == 1
    assert chain.migrate({"schemaVersion": 1}, 1) == {"schemaVersion": 1}


def test_chain_is_frozen_once_sealed() -> None:
    with pytest.raises(MigrationChainError, match="sealed"):
        SAMPLE_MIGRATIONS.step(5)(identity)


def test_unsealed_chain_cannot_be_used() -> None:
    chain = Migrations("x", current=2)
    chain.step(1)(identity)
    with pytest.raises(MigrationChainError, match="before seal"):
        chain.migrate({}, 1)


def test_steps_run_in_order_on_copies() -> None:
    seen: list[int] = []
    chain = Migrations("x", current=3)

    @chain.step(1)
    def one(data: dict[str, Any]) -> dict[str, Any]:
        seen.append(data["schemaVersion"])
        data["one"] = True
        return data

    @chain.step(2)
    def two(data: dict[str, Any]) -> dict[str, Any]:
        seen.append(data["schemaVersion"])
        data["two"] = data["one"]
        return data

    chain.seal()
    original = {"schemaVersion": 1, "nested": {"a": 1}}
    result = chain.migrate(original, 1)
    assert seen == [1, 2]
    assert result == {"schemaVersion": 3, "nested": {"a": 1}, "one": True, "two": True}
    assert original == {"schemaVersion": 1, "nested": {"a": 1}}  # input untouched


def test_project_kind_has_no_steps_yet() -> None:
    assert ProjectFile.MIGRATIONS.current == ProjectFile.SCHEMA_VERSION == 1
    assert ProjectFile.MIGRATIONS.oldest == 1


@pytest.mark.parametrize("model", list(MODELS.values()), ids=list(MODELS))
def test_model_and_chain_agree(model: type[Envelope]) -> None:
    assert model.MIGRATIONS.kind == model.KIND
    assert model.MIGRATIONS.current == model.SCHEMA_VERSION


# AC2: load migrates in memory; a current file is untouched -----------------------------------


def test_load_migrates_in_memory_and_writes_nothing(hostile_dir: Path) -> None:
    path = write(hostile_dir, V0)
    before = snapshot(hostile_dir)
    document = load(path, SampleFile)
    assert document.name == "Équipe sample"
    assert document.tags == ["alpha", "beta"]
    assert document.model_extra == {"userNote": "kept by the migration"}
    assert snapshot(hostile_dir) == before


def test_read_reports_the_old_version(hostile_dir: Path) -> None:
    loaded = read(write(hostile_dir, V0), SampleFile)
    assert loaded.migrated_from == 0
    assert loaded.backup is None


def test_upgrade_of_a_current_file_changes_nothing(hostile_dir: Path) -> None:
    path = write(hostile_dir, (CORPUS / "sample" / "v1" / "basic.json").read_bytes())
    before = snapshot(hostile_dir)
    loaded = upgrade(path, SampleFile, now=NOW)
    assert loaded.migrated_from is None
    assert loaded.backup is None
    assert snapshot(hostile_dir) == before
    assert not (hostile_dir / BACKUP_DIR).exists()


# AC3: upgrade = backup, then atomic rewrite -------------------------------------------------


def test_upgrade_backs_up_then_rewrites(hostile_dir: Path) -> None:
    path = write(hostile_dir, V0)
    loaded = upgrade(path, SampleFile, now=NOW)
    backup = hostile_dir / BACKUP_DIR / "sample.json.v0.20261104T174500Z.json"
    assert loaded.migrated_from == 0
    assert loaded.backup == backup
    assert backup.read_bytes() == V0
    assert path.read_bytes() == (CORPUS / "sample" / "v1" / "basic.json").read_bytes()
    assert sorted(p.name for p in hostile_dir.iterdir()) == [BACKUP_DIR, "sample.json"]  # no temp


def test_two_upgrades_in_the_same_second_keep_both_backups(hostile_dir: Path) -> None:
    path = write(hostile_dir, V0)
    first = upgrade(path, SampleFile, now=NOW).backup
    path.write_bytes(V0.replace("Équipe sample".encode(), b"Second"))
    second = upgrade(path, SampleFile, now=NOW).backup
    assert first is not None and second is not None
    assert first.name == "sample.json.v0.20261104T174500Z.json"
    assert second.name == "sample.json.v0.20261104T174500Z-2.json"
    assert first.read_bytes() == V0
    assert b"Second" in second.read_bytes()


def test_upgraded_file_loads_as_current(hostile_dir: Path) -> None:
    path = write(hostile_dir, V0)
    upgrade(path, SampleFile, now=NOW)
    assert read(path, SampleFile).migrated_from is None


# AC4: too new -----------------------------------------------------------------------------------


def test_too_new_is_never_touched(hostile_dir: Path) -> None:
    path = write(hostile_dir, {"kind": "sample", "schemaVersion": 999, "name": "n"})
    before = snapshot(hostile_dir)
    with pytest.raises(SchemaFileError) as caught:
        upgrade(path, SampleFile, now=NOW)
    assert caught.value.reason is ErrorReason.TOO_NEW
    assert "newer studio" in caught.value.message
    assert snapshot(hostile_dir) == before


def test_older_than_the_chain_is_refused(hostile_dir: Path) -> None:
    path = write(hostile_dir, {"kind": "project", "schemaVersion": 0}, "project.json")
    with pytest.raises(SchemaFileError) as caught:
        upgrade(path, ProjectFile, now=NOW)
    assert caught.value.reason is ErrorReason.INVALID_CONTENT
    assert caught.value.pointer == "/schemaVersion"
    assert "oldest: 1" in caught.value.message


# AC5: a failing step ------------------------------------------------------------------------------


def test_failing_step_leaves_the_file_untouched(hostile_dir: Path) -> None:
    path = write(hostile_dir, {"kind": "sample", "schemaVersion": 0, "tags": "a"})  # no title
    before = snapshot(hostile_dir)
    with pytest.raises(SchemaFileError) as caught:
        upgrade(path, SampleFile, now=NOW)
    error = caught.value
    assert error.reason is ErrorReason.MIGRATION_FAILED
    assert error.pointer == "/schemaVersion"
    assert "sample v0 -> v1 failed: KeyError" in error.message
    assert isinstance(error.__cause__, MigrationStepError)
    assert snapshot(hostile_dir) == before  # no backup, no temp file, same bytes and mtime


def test_step_returning_a_non_object_is_reported() -> None:
    chain = Migrations("x", current=2)
    chain.step(1)(lambda data: None)  # type: ignore[arg-type,return-value]
    chain.seal()
    with pytest.raises(MigrationStepError, match="returned NoneType"):
        chain.migrate({"schemaVersion": 1}, 1)


def test_invalid_after_migration_names_the_origin(hostile_dir: Path) -> None:
    path = write(hostile_dir, {"kind": "sample", "schemaVersion": 0, "title": ""})
    before = snapshot(hostile_dir)
    with pytest.raises(SchemaFileError) as caught:
        upgrade(path, SampleFile, now=NOW)
    assert caught.value.reason is ErrorReason.INVALID_CONTENT
    assert caught.value.pointer == "/name"
    assert "after migrating from v0" in caught.value.message
    assert snapshot(hostile_dir) == before


# AC6: the corpus ----------------------------------------------------------------------------------


def corpus_samples() -> list[Path]:
    return sorted(CORPUS.glob("*/v*/*.json"))


def test_corpus_layout() -> None:
    kinds = {p.name for p in CORPUS.iterdir() if p.is_dir()}
    assert kinds == set(MODELS), "every corpus kind needs a model in MODELS (and vice versa)"
    for kind, model in MODELS.items():
        versions = {int(p.name[1:]) for p in (CORPUS / kind).iterdir() if p.is_dir()}
        expected = set(range(model.MIGRATIONS.oldest, model.SCHEMA_VERSION + 1))
        assert versions == expected, f"{kind}: one corpus folder per readable version"
        for version in versions:
            assert list((CORPUS / kind / f"v{version}").glob("*.json")), f"{kind} v{version} empty"


@pytest.mark.parametrize("sample", corpus_samples(), ids=lambda p: "/".join(p.parts[-3:]))
def test_every_corpus_sample_loads(sample: Path, hostile_dir: Path) -> None:
    kind, version = sample.parts[-3], int(sample.parts[-2][1:])
    copy = write(hostile_dir, sample.read_bytes(), sample.name)
    loaded = read(copy, MODELS[kind])
    assert kind == loaded.document.KIND
    assert loaded.migrated_from == (None if version == MODELS[kind].SCHEMA_VERSION else version)
