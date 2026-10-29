# SPDX-License-Identifier: Apache-2.0
"""Harness self-tests: if these fail, no other result can be trusted (T-30-1, T-30-3)."""

from pathlib import Path

import psutil
import pytest

from conftest import StartBackend
from harness.paths import HOSTILE_NAME, copy_fixture


def _is_our_backend(pid: int) -> bool:
    # A recycled PID belongs to another process; only count it if it still runs the backend.
    try:
        return "studio_backend" in " ".join(psutil.Process(pid).cmdline())
    except psutil.Error:
        return False


@pytest.mark.ac("TC-30", 1)
def test_stop_leaves_no_process_of_the_backend_tree(start_backend_fn: StartBackend) -> None:
    bp = start_backend_fn()
    pids = bp.pids
    assert pids, "the backend tree should have at least one process"

    bp.stop()

    assert [pid for pid in pids if _is_our_backend(pid)] == []


@pytest.mark.ac("TC-30", 3)
def test_hostile_tmp_has_space_and_non_ascii(hostile_tmp: Path) -> None:
    assert " " in hostile_tmp.name and not hostile_tmp.name.isascii()
    (hostile_tmp / "é.json").write_text("{}\n", encoding="utf-8")

    assert (hostile_tmp / "é.json").read_text(encoding="utf-8") == "{}\n"


@pytest.mark.ac("TC-30", 3)
def test_copy_fixture_works_on_a_hostile_copy_not_the_source(tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    source = root / "workspaces" / "demo" / "p" / "project.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}\n", encoding="utf-8")

    copy = copy_fixture("workspaces/demo", tmp_path / "out", fixtures_root=root)
    (copy / "p" / "project.json").write_text("changed\n", encoding="utf-8")

    assert copy.name.startswith(HOSTILE_NAME)
    assert source.read_text(encoding="utf-8") == "{}\n"
