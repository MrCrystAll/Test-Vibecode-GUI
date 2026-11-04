# SPDX-License-Identifier: Apache-2.0
"""Opening a workspace folder (TC-34 AC3, AC4). No HTTP here: TC-35 adds the routes.

`open_workspace(path)` has three outcomes:

- the folder does not exist, or is empty: it is **initialised** (`.studio/` with the marker,
  `trash/` and `cache/`) and opened;
- it has `.studio/workspace.json`: it is **opened** (an older marker is migrated, with a backup);
- anything else (a non-empty folder without the marker, a file): **refused**, and nothing is
  written.

The returned `OpenWorkspace` holds the workspace lock until `close()`; a second open of the same
folder, by this process or another one, raises `WorkspaceInUseError`.
"""

import logging
from pathlib import Path
from types import TracebackType
from typing import Self

from studio_config_schema import SchemaFileError, WorkspaceMarker, loads, save, upgrade

from studio_backend.workspace import layout
from studio_backend.workspace.errors import (
    WorkspaceInvalidError,
    WorkspaceNotAFolderError,
    WorkspaceNotEmptyError,
)
from studio_backend.workspace.lock import WorkspaceLock

log = logging.getLogger(__name__)

NEW_MARKER = '{"kind": "workspace", "schemaVersion": 1}'


class OpenWorkspace:
    """An open workspace: its root and the lock that keeps other backends out."""

    def __init__(self, root: Path, fs_root: Path, lock: WorkspaceLock, *, created: bool) -> None:
        self.root = root
        """The absolute path, as shown to users."""
        self.fs_root = fs_root
        """The same folder for file-system calls (`layout.os_path`: long-path safe on Windows)."""
        self.created = created
        """True when this open initialised the folder."""
        self._lock = lock

    @property
    def is_open(self) -> bool:
        return self._lock.held

    def close(self) -> None:
        self._lock.release()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def open_workspace(path: Path) -> OpenWorkspace:
    """Open (or initialise) the workspace at `path`. See the module docstring for the outcomes."""
    root = Path(path).absolute()
    fs_root = layout.os_path(root)
    marker = layout.marker_path(fs_root)

    if fs_root.exists() and not fs_root.is_dir():
        raise WorkspaceNotAFolderError(root, "is a file, not a folder")
    has_marker = marker.is_file()
    if not has_marker and fs_root.is_dir() and not _is_empty(fs_root):
        raise WorkspaceNotEmptyError(
            root,
            f"the folder is not empty and is not a studio workspace (no {layout.STUDIO_DIR}/"
            f"{layout.MARKER_FILE}); pick an empty folder or an existing workspace",
        )
    if has_marker:
        _check_marker(root, marker)  # refuse a broken or too-new marker before taking anything

    # From here on we may write. Take the lock first, so two backends never initialise together.
    layout.studio_dir(fs_root).mkdir(parents=True, exist_ok=True)
    lock = WorkspaceLock(layout.lock_path(fs_root), shown_path=root)
    lock.acquire()
    try:
        created = not marker.is_file()  # re-checked under the lock
        if created:
            save(marker, loads(NEW_MARKER, WorkspaceMarker))
            log.info("workspace initialised: %s", root)
        else:
            _upgrade_marker(root, marker)
            log.info("workspace opened: %s", root)
        for folder in (layout.TRASH_DIR, layout.CACHE_DIR):
            (layout.studio_dir(fs_root) / folder).mkdir(exist_ok=True)
    except BaseException:
        lock.release()
        raise
    return OpenWorkspace(root, fs_root, lock, created=created)


def _is_empty(fs_root: Path) -> bool:
    """Empty, or holding only a `.studio/` folder without a marker.

    The second case is an initialisation that was interrupted (e.g. the backend was killed between
    creating `.studio/` and writing the marker): finishing it is safe, refusing it would strand the
    user with a folder the studio made but no longer accepts.
    """
    entries = list(fs_root.iterdir())
    return not entries or (
        len(entries) == 1 and entries[0].name == layout.STUDIO_DIR and entries[0].is_dir()
    )


def _check_marker(root: Path, marker: Path) -> None:
    try:
        loads(marker.read_bytes(), WorkspaceMarker, path=marker)
    except SchemaFileError as exc:
        raise _invalid(root, exc) from None


def _upgrade_marker(root: Path, marker: Path) -> None:
    try:
        loaded = upgrade(marker, WorkspaceMarker)
    except SchemaFileError as exc:
        raise _invalid(root, exc) from None
    if loaded.backup is not None:
        log.info(
            "workspace marker migrated from v%s, original kept at %s",
            loaded.migrated_from,
            loaded.backup,
        )


def _invalid(root: Path, exc: SchemaFileError) -> WorkspaceInvalidError:
    where = f"{layout.STUDIO_DIR}/{layout.MARKER_FILE}"
    return WorkspaceInvalidError(root, f"{where} cannot be read: {exc.message}", exc.reason.value)
