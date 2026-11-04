# SPDX-License-Identifier: Apache-2.0
"""Project ids: deriving one from a display name, and checking one a user typed.

Rules decided by the PO on TC-42 (Q3):

- A **derived** id (create without `id`): NFKD, drop combining marks, lowercase, every run of other
  characters becomes `-`, trim `-`, cut to 64 characters, trim `-` again. An empty result becomes
  `project`; a Windows reserved name gets `-project` appended (`con-project`); a taken id
  (case-insensitive) gets `-2`, `-3`, ... A derived id never fails.
- An **explicit** id is never altered: it is valid or it is refused, naming the broken rule.
"""

import re
import unicodedata
from collections.abc import Iterable

from studio_config_schema.project import PROJECT_ID_PATTERN

MAX_ID_LENGTH = 64
FALLBACK_ID = "project"
RESERVED_SUFFIX = "-project"

WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{n}" for n in range(1, 10)}
    | {f"lpt{n}" for n in range(1, 10)}
)
"""Folder names Windows refuses (any case, with or without an extension)."""

_ID = re.compile(PROJECT_ID_PATTERN)
_OTHER = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_ish = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    slug = _OTHER.sub("-", ascii_ish).strip("-")
    return slug[:MAX_ID_LENGTH].strip("-")


def derive_project_id(name: str, taken: Iterable[str] = ()) -> str:
    """The id for a project created from `name`, avoiding every id in `taken` (case-insensitive).

    `Équipe 7` -> `equipe-7`; `日本語` -> `project`; `Con` -> `con-project`; a second `Équipe 7`
    -> `equipe-7-2`.
    """
    base = _slug(name) or FALLBACK_ID
    if base in WINDOWS_RESERVED_NAMES:
        base += RESERVED_SUFFIX
    used = {item.lower() for item in taken}
    if base not in used:
        return base
    counter = 2
    while True:
        suffix = f"-{counter}"
        candidate = base[: MAX_ID_LENGTH - len(suffix)].rstrip("-") + suffix
        if candidate not in used:
            return candidate
        counter += 1


def project_id_problem(project_id: str) -> str | None:
    """Why `project_id` is not a valid project id, or `None` when it is."""
    if not 1 <= len(project_id) <= MAX_ID_LENGTH:
        return f"must be 1 to {MAX_ID_LENGTH} characters long"
    if not _ID.match(project_id):
        return "may only contain lowercase letters a-z, digits 0-9 and '-'"
    if project_id in WINDOWS_RESERVED_NAMES:
        return f"{project_id!r} is a reserved name on Windows"
    return None


def is_taken(project_id: str, taken: Iterable[str]) -> bool:
    """Whether `project_id` collides with an id in `taken`, ignoring case (Windows folders)."""
    return project_id.lower() in {item.lower() for item in taken}
