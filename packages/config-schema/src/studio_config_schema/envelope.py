# SPDX-License-Identifier: Apache-2.0
"""The envelope every studio file shares: `kind` + `schemaVersion` (ADR-0002, TC-32).

A file type is one `Envelope` subclass that sets `KIND`, `SCHEMA_VERSION` and narrows the two fields
to literals. The project file is the first (`project.py`); the workspace marker and app settings
(TC-34) and `run.json` (0.4.0) follow the same pattern.

`schemaVersion` is a per-file-type integer counting up from 1 during 0.x; at 1.0.0 the versions in
use are frozen as the public baseline (PO decision, TC-32).
"""

from datetime import UTC, datetime
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, field_validator

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _parse_timestamp(value: Any) -> datetime:
    """Accept an ISO-8601 string with an offset; normalise to UTC, whole seconds.

    Lenient on load (Q5 on TC-42): fractional seconds and `+00:00` (or any offset) are accepted; the
    next save writes `YYYY-MM-DDTHH:MM:SSZ`. A timestamp without an offset is refused: its time zone
    would be a guess.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("must be an ISO-8601 date-time, e.g. 2026-01-01T00:00:00Z") from None
    else:
        raise ValueError("must be an ISO-8601 date-time string, e.g. 2026-01-01T00:00:00Z")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("must include a UTC offset, e.g. 2026-01-01T00:00:00Z")
    return parsed.astimezone(UTC).replace(microsecond=0)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


UtcTimestamp = Annotated[
    datetime,
    BeforeValidator(_parse_timestamp),
    PlainSerializer(_format_timestamp, return_type=str, when_used="json"),
]
"""A UTC instant, written as `YYYY-MM-DDTHH:MM:SSZ`."""


class Envelope(BaseModel):
    """Base of every studio file.

    **Unknown top-level keys are kept** (`extra="allow"`): load then save gives the same data, so a
    newer studio's fields and a user's hand-added keys are never lost (TC-32 AC2). They are not
    validated and are written back as they were.

    Validation is strict: `"1"` is not an integer and `"yes"` is not a boolean, because a file a
    user edited by hand should be reported, not silently reinterpreted.
    """

    model_config = ConfigDict(
        extra="allow",
        strict=True,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )

    KIND: ClassVar[str]
    """Value of `kind` for this file type."""
    SCHEMA_VERSION: ClassVar[int]
    """The newest `schemaVersion` this studio reads and writes for this file type."""

    kind: str = Field(description="File type. Tells studio files apart without relying on names.")
    schema_version: int = Field(
        alias="schemaVersion",
        ge=1,
        description="Version of this file type's format: an integer counting up from 1.",
    )

    @field_validator("schema_version", mode="before")
    @classmethod
    def _integer_only(cls, value: Any) -> Any:
        # Literal[1] and strict int both let `true` and `1.0` through (they compare equal to 1).
        if type(value) is not int:
            raise ValueError("must be an integer")
        return value
