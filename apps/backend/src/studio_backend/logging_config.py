# SPDX-License-Identifier: Apache-2.0
"""Structured logging: one JSON object per line on stderr.

stdout is reserved for machine-readable events (the handshake), so nothing here writes to it.
"""

import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TextIO

# Loggers that uvicorn sets up on its own; we route them through our handler instead.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


REDACTED = "***"


class JsonFormatter(logging.Formatter):
    """One JSON object per record. Every string in `secrets` is replaced by `***` (TC-19)."""

    def __init__(self, secrets: Sequence[str] = ()) -> None:
        super().__init__()
        self.secrets = tuple(s for s in secrets if s)

    def _redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, REDACTED)
        return text

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": self._redact(record.getMessage()),
        }
        if record.exc_info:
            entry["exc_info"] = self._redact(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(
    level: str, stream: TextIO | None = None, secrets: Sequence[str] = ()
) -> None:
    """Send all logs, including uvicorn's, as JSON lines to `stream` (default: stderr).

    `secrets` (the API token) never appear in the output, e.g. in an access-log query string.
    """
    handler = logging.StreamHandler(sys.stderr if stream is None else stream)
    handler.setFormatter(JsonFormatter(secrets))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
