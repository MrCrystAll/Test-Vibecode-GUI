# SPDX-License-Identifier: Apache-2.0
"""The one error type raised when a studio file cannot be loaded (TC-32 AC5)."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ErrorReason(StrEnum):
    """Why a file was refused. Stable values: the backend maps them to API error codes."""

    INVALID_JSON = "invalid_json"
    """Not decodable as UTF-8 JSON: empty file, syntax error, NaN/Infinity, bad encoding."""
    INVALID_CONTENT = "invalid_content"
    """Valid JSON, but not a valid document: not an object, missing field, wrong type or value."""
    TOO_NEW = "too_new"
    """`schemaVersion` is newer than this studio supports: written by a newer studio."""
    MIGRATION_FAILED = "migration_failed"
    """An older file could not be migrated; the message names the failing step (`v0 -> v1`)."""


@dataclass(frozen=True)
class Issue:
    """One problem in a document, at an RFC 6901 JSON pointer (`""` is the whole document)."""

    pointer: str
    message: str


class SchemaFileError(Exception):
    """A studio file could not be loaded.

    Raised for every content problem: bad JSON, a wrong shape, a missing field, a wrong type or a
    `schemaVersion` newer than supported. File-system errors (missing file, permission denied) are
    not content problems and propagate as `OSError`.

    Attributes:
        path: the file, or `None` when loading from memory.
        reason: the category (see `ErrorReason`).
        issues: every problem found, at least one. `pointer` and `message` describe the first one.
    """

    def __init__(self, path: Path | None, reason: ErrorReason, issues: list[Issue]) -> None:
        if not issues:
            raise ValueError("a SchemaFileError needs at least one issue")
        self.path = path
        self.reason = reason
        self.issues: tuple[Issue, ...] = tuple(issues)
        super().__init__(str(self))

    @property
    def pointer(self) -> str:
        return self.issues[0].pointer

    @property
    def message(self) -> str:
        return self.issues[0].message

    def __str__(self) -> str:
        where = str(self.path) if self.path is not None else "<memory>"
        details = "; ".join(f"{i.pointer or '/'}: {i.message}" for i in self.issues)
        return f"{where}: {details}"


def json_pointer(location: tuple[int | str, ...]) -> str:
    """RFC 6901 pointer for a path of keys and list indices: `("a/b", 0)` -> `/a~1b/0`."""
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in location)
