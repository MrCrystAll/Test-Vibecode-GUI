# SPDX-License-Identifier: Apache-2.0
"""Start the real backend as a subprocess, read its handshake, stop it without leftovers.

Black-box on purpose: the only things used are the documented command line, the stdout
handshake line, stderr log lines and HTTP. Nothing from apps/ or packages/ is imported
(TC-30 AC2).
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

import psutil

REPO_ROOT = Path(__file__).resolve().parents[3]

# The documented dev command (apps/backend/README.md, ADR-0005 dev mode).
# `--frozen`: never touch uv.lock.
DEFAULT_COMMAND = [
    "uv",
    "run",
    "--frozen",
    "--package",
    "studio-backend",
    "python",
    "-m",
    "studio_backend",
]
# Override with a JSON array, e.g. to test another build:
#   STUDIO_API_TEST_BACKEND_CMD='["path/python", "-m", "studio_backend"]'
COMMAND_ENV_VAR = "STUDIO_API_TEST_BACKEND_CMD"

HANDSHAKE_TIMEOUT_S = 60.0  # first run may have to sync the venv
STOP_TIMEOUT_S = 10.0


class BackendError(RuntimeError):
    """The backend did not start, sent a bad handshake, or left processes behind."""


def backend_command() -> list[str]:
    raw = os.environ.get(COMMAND_ENV_VAR)
    if not raw:
        return list(DEFAULT_COMMAND)
    cmd = json.loads(raw)
    if not (isinstance(cmd, list) and cmd and all(isinstance(c, str) for c in cmd)):
        raise BackendError(f"{COMMAND_ENV_VAR} must be a non-empty JSON array of strings")
    return cmd


@dataclass
class Handshake:
    """The first stdout line. `token` is None until TC-19 adds it to the handshake."""

    port: int
    token: str | None
    raw: dict[str, object]


@dataclass
class BackendProcess:
    process: subprocess.Popen[str]
    handshake: Handshake
    log_path: Path
    stdout_lines: list[str] = field(default_factory=list)
    stderr_lines: list[str] = field(default_factory=list)
    _tree: list[psutil.Process] = field(default_factory=list)
    _threads: list[threading.Thread] = field(default_factory=list)
    _log: IO[str] | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.handshake.port}"

    @property
    def pids(self) -> list[int]:
        """Every process of the backend tree seen so far (uv, venv launcher, interpreter...)."""
        self._refresh_tree()
        return [p.pid for p in self._tree]

    def stderr_json(self) -> list[dict[str, object]]:
        """stderr lines parsed as JSON; raises if one is not (the backend promises JSON logs)."""
        return [json.loads(line) for line in list(self.stderr_lines) if line.strip()]

    def _refresh_tree(self) -> None:
        known = {p.pid for p in self._tree}
        try:
            root = psutil.Process(self.process.pid)
            for p in [root, *root.children(recursive=True)]:
                if p.pid not in known:
                    self._tree.append(p)
                    known.add(p.pid)
        except psutil.NoSuchProcess:
            pass

    def stop(self) -> None:
        """Stop the whole process tree, then fail loudly if any of it survived.

        On Windows `uv run` gives uv -> venv launcher -> python, and killing uv alone orphans
        the backend (found in TC-17 testing), so every process of the tree is recorded and
        killed. On POSIX the tree first gets SIGTERM through its own process group, so the
        backend can shut down cleanly.
        """
        self._refresh_tree()
        if sys.platform != "win32":
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)
            _, alive = psutil.wait_procs(self._tree, timeout=STOP_TIMEOUT_S)
        else:
            alive = list(self._tree)
        for p in alive:
            with contextlib.suppress(psutil.NoSuchProcess):
                p.kill()
        _, survivors = psutil.wait_procs(self._tree, timeout=STOP_TIMEOUT_S)
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.process.wait(timeout=STOP_TIMEOUT_S)
        for t in self._threads:
            t.join(timeout=STOP_TIMEOUT_S)
        if self._log is not None:
            self._log.close()
        if survivors:
            raise BackendError(f"backend processes survived stop: {[p.pid for p in survivors]}")


def _pump(
    stream: IO[str], sink: list[str], log: IO[str], prefix: str, first: queue.Queue[str] | None
) -> None:
    for line in stream:
        if first is not None:
            first.put(line)
            first = None
        else:
            sink.append(line.rstrip("\n"))
        log.write(f"{prefix} {line}")
        log.flush()
    if first is not None:
        first.put("")  # EOF before the handshake


def start_backend(
    log_dir: Path,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: Path = REPO_ROOT,
) -> BackendProcess:
    """Spawn the backend on `--port 0` (unless args set a port) and wait for the handshake."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"backend-{time.monotonic_ns()}.log"
    args = list(args or [])
    if "--port" not in args:
        args += ["--port", "0"]
    child_env = dict(os.environ)
    child_env.update(env or {})
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    process = subprocess.Popen(
        [*backend_command(), *args],
        cwd=cwd,
        env=child_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        start_new_session=sys.platform != "win32",
    )
    assert process.stdout is not None and process.stderr is not None
    log = log_path.open("w", encoding="utf-8")
    first: queue.Queue[str] = queue.Queue()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    threads = [
        threading.Thread(
            target=_pump, args=(process.stdout, stdout_lines, log, "OUT", first), daemon=True
        ),
        threading.Thread(
            target=_pump, args=(process.stderr, stderr_lines, log, "ERR", None), daemon=True
        ),
    ]
    for t in threads:
        t.start()

    def fail(message: str) -> BackendError:
        bp = BackendProcess(process, Handshake(0, None, {}), log_path, _threads=threads, _log=log)
        try:
            bp.stop()
        except BackendError as exc:
            message += f"; {exc}"
        return BackendError(f"{message} (log: {log_path})")

    try:
        line = first.get(timeout=HANDSHAKE_TIMEOUT_S)
    except queue.Empty:
        raise fail(f"no handshake within {HANDSHAKE_TIMEOUT_S}s") from None
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        raise fail(f"handshake is not JSON: {line!r}") from None
    port = raw.get("port") if isinstance(raw, dict) else None
    if (
        not isinstance(raw, dict)
        or raw.get("event") != "listening"
        or not isinstance(port, int)
        or port <= 0
    ):
        raise fail(f"unexpected handshake: {line!r}")
    token = raw.get("token")
    bp = BackendProcess(
        process,
        Handshake(port=port, token=token if isinstance(token, str) else None, raw=raw),
        log_path,
        stdout_lines,
        stderr_lines,
        _threads=threads,
        _log=log,
    )
    bp._refresh_tree()
    return bp
