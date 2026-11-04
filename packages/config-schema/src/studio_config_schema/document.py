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
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from studio_config_schema.envelope import Envelope
from studio_config_schema.errors import ErrorReason, Issue, SchemaFileError, json_pointer

ENCODING = "utf-8"


def loads[E: Envelope](data: bytes | str, model: type[E], *, path: Path | None = None) -> E:
    """Parse and validate one document. Raises `SchemaFileError` for any content problem."""
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
    _check_version(raw, model, path)
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        issues = [_issue(error) for error in exc.errors(include_url=False)]
        raise SchemaFileError(path, ErrorReason.INVALID_CONTENT, issues) from None


def load[E: Envelope](path: Path, model: type[E]) -> E:
    """Read and validate a file. `OSError` propagates (missing file, permission denied)."""
    return loads(path.read_bytes(), model, path=path)


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


def _check_version(raw: dict[str, Any], model: type[Envelope], path: Path | None) -> None:
    """Report a too-new file as such, before field validation would call it a wrong value."""
    version = raw.get("schemaVersion")
    if type(version) is int and version > model.SCHEMA_VERSION:
        _fail(
            path,
            ErrorReason.TOO_NEW,
            "/schemaVersion",
            f"schemaVersion {version} is newer than this studio supports ({model.SCHEMA_VERSION}): "
            "the file was written by a newer studio; update the studio to open it",
        )


def _issue(error: Any) -> Issue:
    location: tuple[int | str, ...] = tuple(error["loc"])
    message: str = error["msg"]
    if error["type"] == "missing":
        message = "required field is missing"
    return Issue(json_pointer(location), message)


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
