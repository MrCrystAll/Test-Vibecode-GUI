# SPDX-License-Identifier: Apache-2.0
"""TC-34 AC3/AC4: opening a workspace (QA T-34-4, T-34-5, T-34-6 unit part)."""

import json
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from studio_backend.workspace import (
    OpenWorkspace,
    WorkspaceInUseError,
    WorkspaceInvalidError,
    WorkspaceNotAFolderError,
    WorkspaceNotEmptyError,
    open_workspace,
)
from studio_backend.workspace.layout import os_path

QA_WORKSPACES = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "workspaces"
needs_fixtures = pytest.mark.skipif(not QA_WORKSPACES.is_dir(), reason="QA fixtures not present")


@pytest.fixture
def hostile(tmp_path: Path) -> Path:
    """A parent folder whose path has a space and non-ASCII characters (T-34-5)."""
    folder = tmp_path / "studio wörk é 日本"
    folder.mkdir()
    return folder


@pytest.fixture
def opened() -> Iterator[list[OpenWorkspace]]:
    """Workspaces opened by a test, closed at the end even when it fails."""
    workspaces: list[OpenWorkspace] = []
    yield workspaces
    for workspace in workspaces:
        workspace.close()


def snapshot(folder: Path) -> dict[str, tuple[bytes, int]]:
    return {
        p.relative_to(folder).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def listing(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))


def copy_fixture(name: str, target: Path) -> Path:
    shutil.copytree(QA_WORKSPACES / name, target)
    return target


def assert_initialised(root: Path) -> None:
    marker = root / ".studio" / "workspace.json"
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "kind": "workspace",
        "schemaVersion": 1,
    }
    assert marker.read_bytes().endswith(b"}\n")
    assert (root / ".studio" / "trash").is_dir()
    assert (root / ".studio" / "cache").is_dir()
    assert (root / ".studio" / "lock").is_file()


def test_a_missing_folder_is_created_and_initialised(
    hostile: Path, opened: list[OpenWorkspace]
) -> None:
    root = hostile / "new ws" / "nested"

    workspace = open_workspace(root)
    opened.append(workspace)

    assert workspace.created and workspace.is_open
    assert workspace.root == root
    assert_initialised(root)


def test_an_empty_folder_is_initialised(hostile: Path, opened: list[OpenWorkspace]) -> None:
    root = hostile / "empty"
    root.mkdir()

    opened.append(open_workspace(root))

    assert_initialised(root)


def test_an_interrupted_initialisation_is_finished(
    hostile: Path, opened: list[OpenWorkspace]
) -> None:
    root = hostile / "half"
    (root / ".studio").mkdir(parents=True)
    (root / ".studio" / "lock").write_bytes(b"")

    opened.append(open_workspace(root))

    assert_initialised(root)


@needs_fixtures
def test_an_existing_workspace_is_opened_and_its_files_are_not_rewritten(
    hostile: Path, opened: list[OpenWorkspace]
) -> None:
    root = copy_fixture("one-project", hostile / "one project")
    marker = root / ".studio" / "workspace.json"
    project = root / "first-project" / "project.json"
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (marker, project)}

    workspace = open_workspace(root)
    opened.append(workspace)

    assert not workspace.created
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (marker, project)} == before


@needs_fixtures
def test_a_non_empty_folder_without_marker_is_refused_and_nothing_is_written(
    hostile: Path,
) -> None:
    root = copy_fixture("not-a-workspace", hostile / "Documents")
    before = (listing(root), snapshot(root))

    with pytest.raises(WorkspaceNotEmptyError) as caught:
        open_workspace(root)

    assert caught.value.code == "workspace_not_empty"
    assert caught.value.path == root
    assert (listing(root), snapshot(root)) == before


def test_a_folder_with_only_a_hidden_file_is_not_empty(hostile: Path) -> None:
    root = hostile / "dotfile"
    root.mkdir()
    (root / ".gitkeep").write_bytes(b"")

    with pytest.raises(WorkspaceNotEmptyError):
        open_workspace(root)
    assert listing(root) == [".gitkeep"]


def test_a_file_is_refused(hostile: Path) -> None:
    path = hostile / "notes.txt"
    path.write_text("hello", encoding="utf-8")

    with pytest.raises(WorkspaceNotAFolderError) as caught:
        open_workspace(path)
    assert caught.value.code == "workspace_not_a_folder"


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"{not json", "invalid_json"),
        (b'{"kind": "project", "schemaVersion": 1}', "invalid_content"),
        (b'{"kind": "workspace", "schemaVersion": 99}', "too_new"),
    ],
)
def test_a_broken_marker_is_refused_and_nothing_is_written(
    hostile: Path, content: bytes, reason: str
) -> None:
    root = hostile / "broken"
    (root / ".studio").mkdir(parents=True)
    (root / ".studio" / "workspace.json").write_bytes(content)
    before = (listing(root), snapshot(root))

    with pytest.raises(WorkspaceInvalidError) as caught:
        open_workspace(root)

    assert caught.value.code == "workspace_invalid"
    assert caught.value.reason == reason
    assert (listing(root), snapshot(root)) == before  # no lock file, no trash/cache, no rewrite


def test_a_second_open_is_refused_while_the_first_is_open(
    hostile: Path, opened: list[OpenWorkspace]
) -> None:
    root = hostile / "shared"
    first = open_workspace(root)
    opened.append(first)
    marker = root / ".studio" / "workspace.json"
    # (Not a whole-folder snapshot: on Windows the locked byte of .studio/lock cannot be read.)
    marker_before = (marker.read_bytes(), marker.stat().st_mtime_ns)

    with pytest.raises(WorkspaceInUseError):
        open_workspace(root)

    assert first.is_open
    assert (marker.read_bytes(), marker.stat().st_mtime_ns) == marker_before


def test_close_lets_the_workspace_be_opened_again(hostile: Path) -> None:
    root = hostile / "reopen"
    with open_workspace(root) as first:
        assert first.created
    assert not first.is_open

    with open_workspace(root) as second:
        assert not second.created
        assert second.is_open


@pytest.mark.skipif(sys.platform != "win32", reason="MAX_PATH (260) is a Windows limit")
def test_a_path_longer_than_260_characters_works_on_windows(hostile: Path) -> None:
    deep = os_path(hostile)
    for i in range(8):
        deep = deep / f"a rather long folder name number {i} é"
    root = Path(str(deep).removeprefix("\\\\?\\"))  # as a user would give it
    assert len(str(root)) > 260

    with open_workspace(root) as workspace:
        assert workspace.created
        assert (os_path(root) / ".studio" / "workspace.json").is_file()
