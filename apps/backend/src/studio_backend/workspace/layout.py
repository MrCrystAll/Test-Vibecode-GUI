# SPDX-License-Identifier: Apache-2.0
"""The workspace folder layout and the project-id rules (TC-34 AC1; spec:
docs/spec/workspace-layout.md)."""

import os
import re
import sys
import unicodedata
from collections.abc import Iterable
from pathlib import Path

from studio_backend.workspace.errors import InvalidProjectIdError

STUDIO_DIR = ".studio"
MARKER_FILE = "workspace.json"
LOCK_FILE = "lock"
TRASH_DIR = "trash"
CACHE_DIR = "cache"
PROJECT_FILE = "project.json"
RUNS_DIR = "runs"

PROJECT_ID_MAX_LENGTH = 64
FALLBACK_PROJECT_ID = "project"
RESERVED_SUFFIX = "-project"

# Names Windows refuses for a file or folder, whatever the extension (compared lowercase).
WINDOWS_RESERVED_NAMES = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"com{i}" for i in range(1, 10)]
    + [f"lpt{i}" for i in range(1, 10)]
)

_ID_CHARS = re.compile(r"^[a-z0-9-]+$")
_NOT_ID_CHARS = re.compile(r"[^a-z0-9]+")


def studio_dir(root: Path) -> Path:
    return root / STUDIO_DIR


def marker_path(root: Path) -> Path:
    return root / STUDIO_DIR / MARKER_FILE


def lock_path(root: Path) -> Path:
    return root / STUDIO_DIR / LOCK_FILE


def check_project_id(project_id: str) -> None:
    """Raise `InvalidProjectIdError` naming the first broken rule; return when the id is valid."""
    if not project_id:
        raise InvalidProjectIdError(project_id, "must not be empty")
    if len(project_id) > PROJECT_ID_MAX_LENGTH:
        raise InvalidProjectIdError(
            project_id, f"must be at most {PROJECT_ID_MAX_LENGTH} characters"
        )
    if not _ID_CHARS.match(project_id):
        raise InvalidProjectIdError(
            project_id, "may contain only lowercase letters a-z, digits 0-9 and '-'"
        )
    if project_id in WINDOWS_RESERVED_NAMES:
        raise InvalidProjectIdError(project_id, "is a name reserved by Windows")


def derive_project_id(name: str, taken: Iterable[str] = ()) -> str:
    """The id for a project created from its display name only (PO rules, Q3 on TC-42).

    NFKD and drop combining marks, lowercase, each run of other characters becomes `-`, trim `-`,
    cut to 64, trim again. Empty -> `project`; a Windows reserved name gets `-project`; a taken id
    (compared case-insensitively) gets `-2`, `-3`, ... A derived id never collides.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    slug = _NOT_ID_CHARS.sub("-", ascii_only).strip("-")[:PROJECT_ID_MAX_LENGTH].strip("-")
    if not slug:
        slug = FALLBACK_PROJECT_ID
    if slug in WINDOWS_RESERVED_NAMES:
        slug += RESERVED_SUFFIX
    used = {t.lower() for t in taken}
    if slug not in used:
        return slug
    for n in range(2, len(used) + 3):
        suffix = f"-{n}"
        candidate = slug[: PROJECT_ID_MAX_LENGTH - len(suffix)].rstrip("-") + suffix
        if candidate not in used:
            return candidate
    raise AssertionError("unreachable: more candidates than taken ids")  # pragma: no cover


def os_path(path: Path) -> Path:
    """`path` made absolute and, on Windows, in extended-length form (`\\\\?\\C:\\...`).

    The extended form lifts the 260-character MAX_PATH limit even when the machine has
    `LongPathsEnabled=0` (TC-34 AC3). Use it for file-system calls only; show users `path` itself.
    """
    absolute = Path(os.path.abspath(path))
    if sys.platform != "win32":
        return absolute
    text = str(absolute)
    if text.startswith("\\\\?\\"):
        return absolute
    if text.startswith("\\\\"):  # UNC share: \\server\share -> \\?\UNC\server\share
        return Path("\\\\?\\UNC\\" + text[2:])
    return Path("\\\\?\\" + text)
