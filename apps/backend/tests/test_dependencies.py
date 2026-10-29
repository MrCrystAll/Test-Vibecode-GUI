# SPDX-License-Identifier: Apache-2.0
"""The backend never depends on or imports torch, rlgym or rlgym-learn.

Owner decision; see ADR-0004 §8.
"""

import re
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, requires

FORBIDDEN_DISTRIBUTIONS = {"torch", "rlgym", "rlgym-learn", "rlgym-learn-algos"}
FORBIDDEN_MODULES = ("torch", "rlgym", "rlgym_learn", "rlgym_learn_algos")

_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _runtime_requirements(distribution: str) -> list[str]:
    """Names of the non-optional requirements of an installed distribution."""
    try:
        reqs = requires(distribution) or []
    except PackageNotFoundError:
        return []
    names = []
    for req in reqs:
        if "extra ==" in req:
            continue
        match = _NAME.match(req)
        if match:
            names.append(_normalize(match.group(1)))
    return names


def _dependency_closure(root: str) -> set[str]:
    seen: set[str] = set()
    todo = [_normalize(root)]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo.extend(_runtime_requirements(name))
    return seen


def test_dependency_tree_has_no_training_libraries() -> None:
    closure = _dependency_closure("studio-backend")

    assert "fastapi" in closure  # sanity check: the walk really follows dependencies
    assert closure.isdisjoint(FORBIDDEN_DISTRIBUTIONS)


def test_importing_and_running_the_app_loads_no_training_modules() -> None:
    # A fresh interpreter, so modules imported by other tests (or pytest plugins) can't hide a leak.
    code = (
        "import sys\n"
        "from fastapi.testclient import TestClient\n"
        "import studio_backend.__main__\n"
        "from studio_backend.app import create_app\n"
        "TestClient(create_app()).get('/api/health')\n"
        f"leaked = [m for m in sys.modules if m.split('.')[0] in {FORBIDDEN_MODULES!r}]\n"
        "print(','.join(leaked))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=60
    )

    assert result.stdout.strip() == ""
