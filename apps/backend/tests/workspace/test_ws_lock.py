# SPDX-License-Identifier: Apache-2.0
"""TC-34 AC4: the workspace lock (QA T-34-6, unit part). The API and manual parts are QA's."""

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from studio_backend.workspace import WorkspaceInUseError, WorkspaceLock

# A separate process that takes the lock, says so, then waits until it is killed (or its stdin
# closes).
HOLDER = """
import sys
from pathlib import Path
from studio_backend.workspace import WorkspaceLock
lock = WorkspaceLock(Path(sys.argv[1]))
lock.acquire()
print("locked", flush=True)
sys.stdin.read()
"""


@pytest.fixture
def lock_file(tmp_path: Path) -> Path:
    folder = tmp_path / "studio wörk é" / ".studio"
    folder.mkdir(parents=True)
    return folder / "lock"


@pytest.fixture
def holder(lock_file: Path) -> Iterator[subprocess.Popen[str]]:
    """Another process holding the lock. It is a plain python child (no uv wrapper), so killing
    it kills the lock holder itself: no tree to walk (unlike a `uv run` backend, see T-34-6)."""
    process = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(lock_file)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "locked"
    yield process
    process.kill()
    process.wait(timeout=10)


def test_a_second_lock_in_the_same_process_is_refused(lock_file: Path) -> None:
    with WorkspaceLock(lock_file) as first:
        with pytest.raises(WorkspaceInUseError) as caught:
            WorkspaceLock(lock_file).acquire()
        assert first.held
    assert caught.value.code == "workspace_in_use"


def test_released_lock_can_be_taken_again(lock_file: Path) -> None:
    first = WorkspaceLock(lock_file)
    first.acquire()
    first.release()
    first.release()  # idempotent

    with WorkspaceLock(lock_file) as second:
        assert second.held


def test_acquire_twice_on_the_same_object_is_a_no_op(lock_file: Path) -> None:
    with WorkspaceLock(lock_file) as lock:
        lock.acquire()
        assert lock.held


def test_lock_held_by_another_process_is_refused(
    lock_file: Path, holder: subprocess.Popen[str]
) -> None:
    with pytest.raises(WorkspaceInUseError):
        WorkspaceLock(lock_file).acquire()
    assert holder.poll() is None  # the holder is unaffected


def test_lock_of_a_killed_process_is_not_stale(
    lock_file: Path, holder: subprocess.Popen[str]
) -> None:
    holder.kill()  # SIGKILL on Linux, TerminateProcess on Windows: no clean-up code runs
    holder.wait(timeout=10)
    assert lock_file.exists()  # the file stays; only the OS lock counted, and it is gone

    with WorkspaceLock(lock_file) as lock:
        assert lock.held


def test_error_message_shows_the_users_path(lock_file: Path) -> None:
    shown = Path("D:/My workspace")
    with WorkspaceLock(lock_file), pytest.raises(WorkspaceInUseError) as caught:
        WorkspaceLock(lock_file, shown_path=shown).acquire()
    assert caught.value.path == shown
    assert "another studio" in caught.value.message


def test_lock_file_notes_the_holder_pid(lock_file: Path) -> None:
    import os

    with WorkspaceLock(lock_file):
        pass
    assert f"pid {os.getpid()}" in lock_file.read_bytes().decode("ascii")
