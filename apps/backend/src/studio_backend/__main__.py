# SPDX-License-Identifier: Apache-2.0
"""Entry point: `python -m studio_backend [--host H] [--port P] [--log-level L]`."""

import logging
import sys
from collections.abc import Sequence

from studio_backend.logging_config import configure_logging
from studio_backend.server import run
from studio_backend.settings import SettingsError, load_settings


def main(argv: Sequence[str] | None = None) -> int:
    try:
        settings = load_settings(argv)
    except SettingsError as exc:
        print(f"studio_backend: error: {exc}", file=sys.stderr)
        return 2
    configure_logging(settings.log_level, secrets=(settings.token,))
    try:
        run(settings)
    except OSError as exc:
        logging.getLogger("studio_backend").error("Cannot start: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
