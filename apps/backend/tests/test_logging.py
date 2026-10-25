# SPDX-License-Identifier: Apache-2.0
import io
import json
import logging
from collections.abc import Iterator

import pytest

from studio_backend.logging_config import configure_logging


@pytest.fixture
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers, root.level = handlers, level


@pytest.mark.usefixtures("restore_root_logger")
def test_logs_are_json_lines_including_uvicorn() -> None:
    stream = io.StringIO()
    configure_logging("info", stream=stream)

    logging.getLogger("studio_backend.test").info("hello %s", "world")
    logging.getLogger("uvicorn.error").warning("from uvicorn")
    logging.getLogger("studio_backend.test").debug("filtered out by level")

    lines = stream.getvalue().splitlines()
    records = [json.loads(line) for line in lines]
    assert [r["message"] for r in records] == ["hello world", "from uvicorn"]
    assert records[0]["level"] == "info"
    assert records[0]["logger"] == "studio_backend.test"
    assert records[1]["level"] == "warning"
    assert all("ts" in r for r in records)


@pytest.mark.usefixtures("restore_root_logger")
def test_exceptions_are_logged_inside_the_json_line() -> None:
    stream = io.StringIO()
    configure_logging("info", stream=stream)

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logging.getLogger("studio_backend.test").exception("failed")

    (line,) = stream.getvalue().splitlines()
    record = json.loads(line)
    assert record["message"] == "failed"
    assert "RuntimeError: boom" in record["exc_info"]
