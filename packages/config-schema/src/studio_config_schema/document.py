# SPDX-License-Identifier: Apache-2.0
"""Reading and writing studio files (TC-32 AC3, AC5).

Written bytes are deterministic: UTF-8 without a BOM and without `\\u` escapes, LF line ends,
2-space indent, the envelope's top-level keys sorted, one trailing newline. Values inside `upstream`
and inside unknown keys keep their original key order: they are not the studio's to reformat.

Optional fields absent from a file stay absent when it is saved again (`exclude_unset`), so loading
and saving an unchanged file gives the same bytes.

Reading is lenient where editors differ (Q5 on TC-42): a UTF-8 BOM, CRLF line ends, fractional
seconds and `+00:00` offsets are accepted; the next save normalises them.
"""

import json
import math
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from studio_config_schema.envelope import Envelope
from studio_config_schema.errors import ErrorReason, Issue, SchemaFileError, json_pointer
from studio_config_schema.migrations import MigrationStepError

ENCODING = "utf-8"
BACKUP_DIR = ".backup"
"""Folder, next to a migrated file, that keeps the originals (TC-33)."""


@dataclass(frozen=True)
class Loaded[E: Envelope]:
    """A loaded document and what happened on the way."""

    document: E
    migrated_from: int | None = None
    """The file's `schemaVersion` when it was older than current, else `None`."""
    backup: Path | None = None
    """Where `upgrade` copied the original before rewriting it, else `None`."""


def loads[E: Envelope](data: bytes | str, model: type[E], *, path: Path | None = None) -> E:
    """Parse, migrate in memory and validate one document. Raises `SchemaFileError`."""
    return _load(data, model, path).document


def load[E: Envelope](path: Path, model: type[E]) -> E:
    """Read a file, migrating it **in memory only**: the file is never written (read-only callers).

    `OSError` propagates (missing file, permission denied).
    """
    return _load(path.read_bytes(), model, path).document


def read[E: Envelope](path: Path, model: type[E]) -> Loaded[E]:
    """Like `load`, and also tells whether the file was from an older version. Never writes."""
    return _load(path.read_bytes(), model, path)


def upgrade[E: Envelope](path: Path, model: type[E], *, now: datetime | None = None) -> Loaded[E]:
    """Read a file and, if an older version wrote it, migrate it and save it (TC-33).

    Before the rewrite, the original bytes are copied to
    `<folder>/.backup/<file name>.v<old>.<YYYYMMDDTHHMMSSZ>.json`, with `-2`, `-3`... if that
    name is taken. The rewrite is atomic (`save`). A current file is not touched (same bytes,
    same mtime). A too-new, invalid or unmigratable file raises `SchemaFileError` and nothing is
    written.
    """
    original = path.read_bytes()
    loaded = _load(original, model, path)
    if loaded.migrated_from is None:
        return loaded
    backup = _write_backup(path, original, loaded.migrated_from, now or datetime.now(UTC))
    save(path, loaded.document)
    return Loaded(loaded.document, loaded.migrated_from, backup)


def _load[E: Envelope](data: bytes | str, model: type[E], path: Path | None) -> Loaded[E]:
    text = _decode(data, path)
    if not text.strip():
        _fail(path, ErrorReason.INVALID_JSON, "", "the file is empty")
    try:
        raw = json.loads(text, parse_constant=_reject_constant, parse_float=_finite_float)
    except json.JSONDecodeError as exc:
        _fail(
            path,
            ErrorReason.INVALID_JSON,
            "",
            f"not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})",
        )
    except ValueError as exc:
        _fail(path, ErrorReason.INVALID_JSON, "", str(exc))
    if not isinstance(raw, dict):
        _fail(
            path, ErrorReason.INVALID_CONTENT, "", f"must be a JSON object, not {_json_type(raw)}"
        )
    raw, migrated_from = _migrate(raw, model, path)
    try:
        document = model.model_validate(raw)
    except ValidationError as exc:
        after = f" (after migrating from v{migrated_from})" if migrated_from is not None else ""
        issues = [_issue(error, after) for error in exc.errors(include_url=False)]
        raise SchemaFileError(path, ErrorReason.INVALID_CONTENT, issues) from None
    return Loaded(document, migrated_from)


def dumps(document: Envelope) -> str:
    """Serialise a document to its canonical text (see the module docstring)."""
    data: dict[str, Any] = document.model_dump(mode="json", by_alias=True, exclude_unset=True)
    ordered = {key: data[key] for key in sorted(data)}
    return json.dumps(ordered, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def dump_bytes(document: Envelope) -> bytes:
    return dumps(document).encode(ENCODING)


def save(path: Path, document: Envelope) -> None:
    """Write a file atomically: a temporary file in the same folder, flushed, then renamed over."""
    payload = dump_bytes(document)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        # mkstemp creates the file 0600; keep the target's mode (e.g. 0644).
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            tmp.chmod(mode)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _decode(data: bytes | str, path: Path | None) -> str:
    if isinstance(data, str):
        return data.removeprefix("﻿")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        _fail(path, ErrorReason.INVALID_JSON, "", f"not UTF-8 text (byte {exc.start})")


def _finite_float(text: str) -> float:
    """Reject numbers out of float range (`1e400` would load as inf and then fail to save)."""
    value = float(text)
    if math.isinf(value):
        raise ValueError(f"not valid JSON: {text} is out of range for a number")
    return value


def _reject_constant(name: str) -> NoReturn:
    raise ValueError(f"not valid JSON: {name} is not a JSON number")


def _migrate(
    raw: dict[str, Any], model: type[Envelope], path: Path | None
) -> tuple[dict[str, Any], int | None]:
    """Bring an older file up to the current version; refuse a too-new one before validation."""
    version = raw.get("schemaVersion")
    if type(version) is not int:
        return raw, None  # missing or wrong type: field validation reports it
    chain = model.MIGRATIONS
    if version > chain.current:
        _fail(
            path,
            ErrorReason.TOO_NEW,
            "/schemaVersion",
            f"schemaVersion {version} is newer than this studio supports ({chain.current}): "
            "the file was written by a newer studio; update the studio to open it",
        )
    if version == chain.current:
        return raw, None
    if version < chain.oldest:
        _fail(
            path,
            ErrorReason.INVALID_CONTENT,
            "/schemaVersion",
            f"schemaVersion {version} is older than any version this studio reads "
            f"(oldest: {chain.oldest})",
        )
    try:
        return chain.migrate(raw, version), version
    except MigrationStepError as exc:
        issue = Issue("/schemaVersion", str(exc))
        raise SchemaFileError(path, ErrorReason.MIGRATION_FAILED, [issue]) from exc


def _write_backup(path: Path, original: bytes, old_version: int, now: datetime) -> Path:
    folder = path.parent / BACKUP_DIR
    folder.mkdir(exist_ok=True)
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = f"{path.name}.v{old_version}.{stamp}"
    for attempt in range(1, 1000):
        target = folder / (f"{base}.json" if attempt == 1 else f"{base}-{attempt}.json")
        try:
            # "xb": never overwrite an earlier backup, even one made in the same second.
            with target.open("xb") as f:
                f.write(original)
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError:
            continue
        return target
    raise FileExistsError(f"too many backups of {path.name} in {folder} for {stamp}")


def _issue(error: Any, suffix: str = "") -> Issue:
    location: tuple[int | str, ...] = tuple(error["loc"])
    message: str = error["msg"]
    if error["type"] == "missing":
        message = "required field is missing"
    return Issue(json_pointer(location), message + suffix)


def _json_type(value: object) -> str:
    match value:
        case list():
            return "an array"
        case str():
            return "a string"
        case bool():
            return "a boolean"
        case int() | float():
            return "a number"
        case None:
            return "null"
        case _:
            return type(value).__name__


def _fail(path: Path | None, reason: ErrorReason, pointer: str, message: str) -> NoReturn:
    raise SchemaFileError(path, reason, [Issue(pointer, message)])
