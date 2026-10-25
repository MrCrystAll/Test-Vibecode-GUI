# SPDX-License-Identifier: Apache-2.0
"""Runtime settings from CLI arguments and environment variables.

Precedence: CLI argument > environment variable > default. The backend never reads settings
from the current working directory (ADR-0005).
"""

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

ENV_PREFIX = "STUDIO_BACKEND_"
LOG_LEVELS = ("debug", "info", "warning", "error", "critical")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 0
DEFAULT_LOG_LEVEL = "info"


@dataclass(frozen=True)
class Settings:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    log_level: str = DEFAULT_LOG_LEVEL


class SettingsError(ValueError):
    """Raised when a setting has an invalid value."""


def _parse_port(raw: str, source: str) -> int:
    try:
        port = int(raw)
    except ValueError:
        raise SettingsError(f"{source}: port must be an integer, got {raw!r}") from None
    if not 0 <= port <= 65535:
        raise SettingsError(f"{source}: port must be between 0 and 65535, got {port}")
    return port


def _parse_log_level(raw: str, source: str) -> str:
    level = raw.lower()
    if level not in LOG_LEVELS:
        allowed = ", ".join(LOG_LEVELS)
        raise SettingsError(f"{source}: log level must be one of {allowed}, got {raw!r}")
    return level


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio_backend",
        description="Studio backend. Prints one JSON line on stdout once ready: "
        '{"event": "listening", "port": N}.',
    )
    parser.add_argument(
        "--host", help=f"Interface to bind (env {ENV_PREFIX}HOST, default {DEFAULT_HOST})."
    )
    parser.add_argument(
        "--port",
        help=f"Port to bind, 0 = any free port (env {ENV_PREFIX}PORT, default {DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--log-level",
        help=f"One of {', '.join(LOG_LEVELS)} "
        f"(env {ENV_PREFIX}LOG_LEVEL, default {DEFAULT_LOG_LEVEL}).",
    )
    return parser


def load_settings(
    argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
) -> Settings:
    """Build settings from `argv` (default: sys.argv) and `env` (default: os.environ)."""
    args = build_parser().parse_args(argv)
    environ = os.environ if env is None else env

    host = DEFAULT_HOST
    port = DEFAULT_PORT
    log_level = DEFAULT_LOG_LEVEL

    if f"{ENV_PREFIX}HOST" in environ:
        host = environ[f"{ENV_PREFIX}HOST"]
    if f"{ENV_PREFIX}PORT" in environ:
        port = _parse_port(environ[f"{ENV_PREFIX}PORT"], f"{ENV_PREFIX}PORT")
    if f"{ENV_PREFIX}LOG_LEVEL" in environ:
        log_level = _parse_log_level(environ[f"{ENV_PREFIX}LOG_LEVEL"], f"{ENV_PREFIX}LOG_LEVEL")

    if args.host is not None:
        host = args.host
    if args.port is not None:
        port = _parse_port(args.port, "--port")
    if args.log_level is not None:
        log_level = _parse_log_level(args.log_level, "--log-level")

    return Settings(host=host, port=port, log_level=log_level)
