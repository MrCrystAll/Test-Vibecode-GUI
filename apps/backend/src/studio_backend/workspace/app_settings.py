# SPDX-License-Identifier: Apache-2.0
"""The app settings file: current workspace and recent workspaces (TC-34 AC2).

`<settings dir>/settings.json`, a `kind: "app-settings"` envelope
(studio_config_schema.AppSettings).
The settings dir is the OS user config dir from `platformdirs` (e.g. `%APPDATA%\\rlgym-studio` on
Windows, `~/.config/rlgym-studio` on Linux), or `STUDIO_BACKEND_SETTINGS_DIR` when set (tests, or
several isolated studios on one machine). Only the backend reads or writes this file (ADR-0002).

A settings file that cannot be read (bad JSON, wrong content, written by a newer studio) never stops
the studio: it is moved aside to `settings.json.<reason>.<UTC timestamp>.json`, a warning is logged,
and the studio starts from empty settings. Nothing is lost, and the user just picks a workspace
again.
"""

import logging
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import platformdirs
from studio_config_schema import (
    MAX_RECENT_WORKSPACES,
    AppSettings,
    SchemaFileError,
    load,
    loads,
    save,
)

from studio_backend.settings import ENV_PREFIX
from studio_backend.workspace.layout import os_path

log = logging.getLogger(__name__)

APP_DIR_NAME = "rlgym-studio"
SETTINGS_FILE = "settings.json"
SETTINGS_DIR_ENV = f"{ENV_PREFIX}SETTINGS_DIR"
EMPTY = '{"kind": "app-settings", "schemaVersion": 1}'


def settings_dir(env: Mapping[str, str] = os.environ) -> Path:
    """`STUDIO_BACKEND_SETTINGS_DIR` if set and not blank, else the OS user config dir."""
    override = env.get(SETTINGS_DIR_ENV, "").strip()
    if override:
        return Path(override).absolute()
    return Path(platformdirs.user_config_dir(APP_DIR_NAME, appauthor=False))


def same_path(a: str, b: str) -> bool:
    """Whether two remembered paths name the same folder (case-insensitive on Windows)."""
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


class AppSettingsStore:
    """Reads and writes `settings.json` in one settings dir. Writes are atomic (TC-32 `save`)."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / SETTINGS_FILE
        self._fs_path = os_path(self.path)

    def load(self) -> AppSettings:
        """The current settings; empty ones when there is no file yet or it was unreadable."""
        if not self._fs_path.is_file():
            return loads(EMPTY, AppSettings)
        try:
            return load(self._fs_path, AppSettings)
        except SchemaFileError as exc:
            aside = self._move_aside(exc.reason.value)
            log.warning(
                "app settings unreadable (%s: %s); moved to %s, starting from empty settings",
                exc.reason.value,
                exc.message,
                aside,
            )
            return loads(EMPTY, AppSettings)

    def save(self, settings: AppSettings) -> None:
        self._fs_path.parent.mkdir(parents=True, exist_ok=True)
        save(self._fs_path, settings)

    def remember_workspace(self, workspace: Path) -> AppSettings:
        """Make `workspace` the current one and first in the recent list, then save."""
        settings = self.load()
        path = str(workspace)
        recent = [path] + [p for p in settings.recent_workspaces if not same_path(p, path)]
        updated = settings.model_copy(
            update={
                "current_workspace": path,
                "recent_workspaces": recent[:MAX_RECENT_WORKSPACES],
            }
        )
        self.save(updated)
        return updated

    def forget_workspace(self, workspace: Path) -> AppSettings:
        """Drop `workspace` from the recent list (and as current), e.g. when it no longer exists."""
        settings = self.load()
        path = str(workspace)
        current = settings.current_workspace
        updated = settings.model_copy(
            update={
                "current_workspace": None if current and same_path(current, path) else current,
                "recent_workspaces": [
                    p for p in settings.recent_workspaces if not same_path(p, path)
                ],
            }
        )
        self.save(updated)
        return updated

    def _move_aside(self, reason: str) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        for attempt in range(1, 1000):
            suffix = "" if attempt == 1 else f"-{attempt}"
            target = self._fs_path.with_name(f"{SETTINGS_FILE}.{reason}.{stamp}{suffix}.json")
            if not target.exists():
                self._fs_path.replace(target)
                return target
        raise FileExistsError(f"too many unreadable settings files moved aside in {self.directory}")
