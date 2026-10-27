# SPDX-License-Identifier: Apache-2.0
"""Runtime settings from CLI arguments and environment variables.

Precedence: CLI argument > environment variable > default. The backend never reads settings
from the current working directory (ADR-0005).

The token is read from the environment only, never from the command line, because command lines
are visible to every local user (process lists).
"""

import argparse
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from studio_backend.security import generate_token

ENV_PREFIX = "STUDIO_BACKEND_"
LOG_LEVELS = ("debug", "info", "warning", "error", "critical")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 0
DEFAULT_LOG_LEVEL = "info"
DEFAULT_WS_PING_INTERVAL = 15.0
MIN_TOKEN_LENGTH = 32
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-.~]+")  # safe in a header and a query string
_TRUE = ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    log_level: str = DEFAULT_LOG_LEVEL
    token: str = field(default_factory=generate_token, repr=False)
    allowed_origins: tuple[str, ...] = ()
    unsafe_bind_any: bool = False
    ws_ping_interval: float = DEFAULT_WS_PING_INTERVAL


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


def _parse_token(raw: str, source: str) -> str:
    if len(raw) < MIN_TOKEN_LENGTH or not _TOKEN_PATTERN.fullmatch(raw):
        raise SettingsError(
            f"{source}: token must be at least {MIN_TOKEN_LENGTH} characters of A-Z a-z 0-9 - _ . ~"
        )
    return raw


def _parse_interval(raw: str, source: str) -> float:
    try:
        seconds = float(raw)
    except ValueError:
        raise SettingsError(
            f"{source}: interval must be a number of seconds, got {raw!r}"
        ) from None
    if not 0 < seconds <= 3600:
        raise SettingsError(f"{source}: interval must be > 0 and <= 3600 seconds, got {raw!r}")
    return seconds


def _parse_origins(raw: str) -> tuple[str, ...]:
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio_backend",
        description="Studio backend. Prints one JSON line on stdout once ready: "
        '{"event": "listening", "port": N, "token": "..."}. '
        f"The token comes from {ENV_PREFIX}TOKEN, or is generated.",
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
    parser.add_argument(
        "--allowed-origin",
        action="append",
        help="Browser origin allowed to call the API, repeatable "
        f"(env {ENV_PREFIX}ALLOWED_ORIGINS, comma-separated; default none).",
    )
    parser.add_argument(
        "--ws-ping-interval",
        help="Seconds between WebSocket pings "
        f"(env {ENV_PREFIX}WS_PING_INTERVAL, default {DEFAULT_WS_PING_INTERVAL:g}).",
    )
    parser.add_argument(
        "--unsafe-bind-any",
        action="store_true",
        default=None,
        help=f"Development only: allow --host other than {DEFAULT_HOST} "
        f"(env {ENV_PREFIX}UNSAFE_BIND_ANY=1).",
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
    allowed_origins: tuple[str, ...] = ()
    ws_ping_interval = DEFAULT_WS_PING_INTERVAL
    unsafe_bind_any = environ.get(f"{ENV_PREFIX}UNSAFE_BIND_ANY", "").lower() in _TRUE
    token = (
        _parse_token(environ[f"{ENV_PREFIX}TOKEN"], f"{ENV_PREFIX}TOKEN")
        if f"{ENV_PREFIX}TOKEN" in environ
        else generate_token()
    )

    if f"{ENV_PREFIX}HOST" in environ:
        host = environ[f"{ENV_PREFIX}HOST"]
    if f"{ENV_PREFIX}PORT" in environ:
        port = _parse_port(environ[f"{ENV_PREFIX}PORT"], f"{ENV_PREFIX}PORT")
    if f"{ENV_PREFIX}LOG_LEVEL" in environ:
        log_level = _parse_log_level(environ[f"{ENV_PREFIX}LOG_LEVEL"], f"{ENV_PREFIX}LOG_LEVEL")
    if f"{ENV_PREFIX}WS_PING_INTERVAL" in environ:
        ws_ping_interval = _parse_interval(
            environ[f"{ENV_PREFIX}WS_PING_INTERVAL"], f"{ENV_PREFIX}WS_PING_INTERVAL"
        )
    if f"{ENV_PREFIX}ALLOWED_ORIGINS" in environ:
        allowed_origins = _parse_origins(environ[f"{ENV_PREFIX}ALLOWED_ORIGINS"])

    if args.host is not None:
        host = args.host
    if args.port is not None:
        port = _parse_port(args.port, "--port")
    if args.log_level is not None:
        log_level = _parse_log_level(args.log_level, "--log-level")
    if args.allowed_origin is not None:
        allowed_origins = tuple(args.allowed_origin)
    if args.ws_ping_interval is not None:
        ws_ping_interval = _parse_interval(args.ws_ping_interval, "--ws-ping-interval")
    if args.unsafe_bind_any is not None:
        unsafe_bind_any = True

    if host != DEFAULT_HOST and not unsafe_bind_any:
        raise SettingsError(
            f"host must be {DEFAULT_HOST} (got {host!r}); binding elsewhere exposes the API to "
            f"other machines and needs --unsafe-bind-any / {ENV_PREFIX}UNSAFE_BIND_ANY=1"
        )

    return Settings(
        host=host,
        port=port,
        log_level=log_level,
        token=token,
        allowed_origins=allowed_origins,
        unsafe_bind_any=unsafe_bind_any,
        ws_ping_interval=ws_ping_interval,
    )
