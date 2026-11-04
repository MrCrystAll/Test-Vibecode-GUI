# SPDX-License-Identifier: Apache-2.0
"""The workspace lock: an OS-level lock on `<workspace>/.studio/lock` (TC-34 AC4).

Standard library only: `fcntl.flock` on Linux/macOS, `msvcrt.locking` on Windows. Both are held by
an open file handle and **released by the OS when the process dies**, however it dies (kill -9,
Task Manager, crash). So a lock left by a killed backend is never stale: the next open just takes
it. The lock file itself may stay on disk; its presence means nothing, only the OS lock does.

Both kinds of lock also conflict between two handles of the same process, which the unit tests use.
"""

import os
import sys
from pathlib import Path
from types import TracebackType
from typing import IO, Self

from studio_backend.workspace.errors import WorkspaceInUseError

if sys.platform == "win32":
    import msvcrt

    def _try_lock(handle: IO[bytes]) -> bool:
        handle.seek(0)
        try:
            # One byte at offset 0, non-blocking. Locking past the end of an empty file is allowed.
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(handle: IO[bytes]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(handle: IO[bytes]) -> bool:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class WorkspaceLock:
    """Holds the OS lock on one lock file until `release()` (or the end of a `with` block).

    `shown_path` is the path used in error messages (the user's spelling, not the `\\\\?\\` form).
    """

    def __init__(self, path: Path, *, shown_path: Path | None = None) -> None:
        self.path = path
        self.shown_path = shown_path or path
        self._handle: IO[bytes] | None = None

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self) -> None:
        """Take the lock or raise `WorkspaceInUseError` at once (never waits)."""
        if self._handle is not None:
            return
        # "a+b": create the file if needed, never truncate it, and work on Windows and Linux alike.
        handle = open(self.path, "a+b")  # noqa: SIM115 - kept open while the lock is held
        if not _try_lock(handle):
            handle.close()
            raise WorkspaceInUseError(
                self.shown_path,
                "the workspace is open in another studio window or backend "
                f"(process lock on {self.path.name} is held); close it there first",
            )
        self._handle = handle
        self._write_owner(handle)

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            _unlock(handle)
        finally:
            handle.close()

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()

    @staticmethod
    def _write_owner(handle: IO[bytes]) -> None:
        """Note who holds the lock, for people looking at the folder. Never read back by the code.

        Written after offset 0 so it never touches the locked byte on Windows.
        """
        try:
            handle.truncate(1)
            handle.seek(1)
            handle.write(f"\npid {os.getpid()}\n".encode("ascii"))
            handle.flush()
        except OSError:
            pass  # informational only
