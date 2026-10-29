# SPDX-License-Identifier: Apache-2.0
"""Temp directories and fixture copies for black-box tests (test strategy §5)."""

from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"

# A space and non-ASCII characters in every temp path, so path bugs show up on both OSes
# (strategy §5.3).
HOSTILE_NAME = "ws é ü 1"


def hostile_dir(parent: Path, name: str = HOSTILE_NAME) -> Path:
    path = parent / name
    path.mkdir(parents=True, exist_ok=False)
    return path


def copy_fixture(relative: str, dest_parent: Path, fixtures_root: Path = FIXTURES_ROOT) -> Path:
    """Copy `tests/fixtures/<relative>` into a new hostile folder under `dest_parent`.

    Fixtures are read-only inputs: tests always work on the returned copy, never on the
    committed files (strategy §5.1).
    """
    source = fixtures_root / relative
    if not source.is_dir():
        raise FileNotFoundError(f"no fixture folder {source}")
    dest = hostile_dir(dest_parent, f"{HOSTILE_NAME} {Path(relative).name}")
    shutil.copytree(source, dest, dirs_exist_ok=True)
    return dest


def workspace_from_fixture(name: str, dest_parent: Path) -> Path:
    """A temp copy of `tests/fixtures/workspaces/<name>/` (0.2.0+)."""
    return copy_fixture(f"workspaces/{name}", dest_parent)
