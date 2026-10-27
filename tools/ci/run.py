# SPDX-License-Identifier: Apache-2.0
"""Run the repository checks, the same way locally and in CI.

Usage (from anywhere in the repo):

    uv run --no-project python tools/ci/run.py <step> [<step> ...]

Steps: install, lint, typecheck, test, build, hooks, or `all` (every step in that order).

What runs is discovered, so new apps and packages plug in without editing this file:
- uv workspace members (root pyproject.toml): ruff if `[tool.ruff]`, mypy if `[tool.mypy]`, pytest if a `tests/`
  folder or `[tool.pytest.ini_options]` exists, `uv build` if `[build-system]`;
- pnpm workspace members: their `lint`, `typecheck`, `test` and `build` package.json scripts, when present;
- hooks: each script in HOOKS, when the file exists.

Every skipped check is printed, so a missing test run is visible in the log. pytest runs with
`--basetemp=.ci-tmp/pytest/<member>`, so CI can upload what the tests leave there (e.g. backend logs) on failure.

Standard library only, so it runs before anything is installed.
"""

import os
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTEST_TMP = ROOT / ".ci-tmp" / "pytest"
STEPS = ("install", "lint", "typecheck", "test", "build", "hooks")
# Checks owned by other stories: (name, script relative to the repo root, arguments).
# Each runs only once its script exists.
HOOKS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # TC-18: openapi.json and the generated client match the code
    ("contract-drift", "tools/ci/hooks/contract-drift.py", ()),
    # TC-25: ADR-0001 / ADR-0004 import rules
    ("import-boundaries", "tools/ci/hooks/import-boundaries.py", ()),
    # TC-42: the committed workspace fixtures match their generator
    ("workspace-fixtures", "tests/fixtures/workspaces/generate.py", ("--check",)),
    # TC-28: every dependency's licence is on the allow-list in tools/ci/licenses.toml
    ("licenses", "tools/ci/hooks/licenses.py", ()),
)
IN_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


@dataclass(frozen=True)
class UvMember:
    name: str
    path: Path
    has_ruff: bool
    has_mypy: bool
    has_tests: bool
    is_buildable: bool


def load_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as f:
        return tomllib.load(f)


def _table(data: dict[str, object], *keys: str) -> dict[str, object]:
    """Return a nested TOML table, or an empty dict when any level is missing."""
    current: object = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return {}
        current = current[key]
    return current if isinstance(current, dict) else {}


def uv_members(root: Path = ROOT) -> list[UvMember]:
    """Workspace members listed in the root pyproject.toml (glob patterns allowed)."""
    patterns = _table(load_toml(root / "pyproject.toml"), "tool", "uv", "workspace").get(
        "members", []
    )
    if not isinstance(patterns, list):
        raise SystemExit("[tool.uv.workspace] members must be a list")
    members = []
    for pattern in patterns:
        for path in sorted(root.glob(str(pattern))):
            manifest = path / "pyproject.toml"
            if not manifest.is_file():
                continue
            data = load_toml(manifest)
            members.append(
                UvMember(
                    name=str(_table(data, "project").get("name", path.name)),
                    path=path,
                    has_ruff=bool(_table(data, "tool", "ruff")),
                    has_mypy=bool(_table(data, "tool", "mypy")),
                    has_tests=(path / "tests").is_dir()
                    or bool(_table(data, "tool", "pytest", "ini_options")),
                    is_buildable=bool(_table(data, "build-system")),
                )
            )
    return members


def pnpm_command() -> list[str]:
    """`pnpm` if it is on PATH, otherwise the Corepack-managed one."""
    pnpm = shutil.which("pnpm")
    if pnpm:
        return [pnpm]
    corepack = shutil.which("corepack")
    if corepack:
        return [corepack, "pnpm"]
    raise SystemExit("pnpm not found: install Node.js 24 and run `corepack enable`")


def uv_command() -> list[str]:
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit(
            "uv not found: see https://docs.astral.sh/uv/getting-started/installation/"
        )
    return [uv]


class Runner:
    """Runs commands, keeps going after a failure, and reports every failure at the end."""

    def __init__(self) -> None:
        self.failures: list[str] = []

    def run(self, title: str, command: Sequence[str], cwd: Path = ROOT) -> None:
        if IN_GITHUB_ACTIONS:
            print(f"::group::{title}", flush=True)
        else:
            print(f"\n=== {title}", flush=True)
        print(f"$ {' '.join(command)}  (in {cwd.relative_to(ROOT).as_posix() or '.'})", flush=True)
        result = subprocess.run(command, cwd=cwd, check=False)  # noqa: S603 - fixed tool commands
        if IN_GITHUB_ACTIONS:
            print("::endgroup::", flush=True)
        if result.returncode != 0:
            self.failures.append(f"{title} (exit {result.returncode})")
            if IN_GITHUB_ACTIONS:
                print(f"::error::{title} failed with exit code {result.returncode}", flush=True)


def step_install(runner: Runner) -> None:
    runner.run("uv sync", [*uv_command(), "sync", "--all-packages", "--locked"])
    runner.run("pnpm install", [*pnpm_command(), "install", "--frozen-lockfile"])


def _uv_tool(member: UvMember, *args: str) -> list[str]:
    return [*uv_command(), "run", "--locked", "--package", member.name, *args]


def _pnpm_script(script: str) -> list[str]:
    return [*pnpm_command(), "--recursive", "--if-present", "run", script]


def step_lint(runner: Runner) -> None:
    for member in uv_members():
        if member.has_ruff:
            runner.run(
                f"ruff check: {member.name}", _uv_tool(member, "ruff", "check", "."), member.path
            )
            runner.run(
                f"ruff format: {member.name}",
                _uv_tool(member, "ruff", "format", "--check", "."),
                member.path,
            )
    runner.run("pnpm lint", _pnpm_script("lint"))


def step_typecheck(runner: Runner) -> None:
    for member in uv_members():
        if member.has_mypy:
            runner.run(f"mypy: {member.name}", _uv_tool(member, "mypy"), member.path)
    runner.run("pnpm typecheck", _pnpm_script("typecheck"))


def step_test(runner: Runner) -> None:
    runner.run(
        "tools/ci self-test",
        [sys.executable, "-m", "unittest", "discover", "-s", "tools/ci/tests", "-t", "."],
    )
    # pytest creates --basetemp itself but not its parents.
    PYTEST_TMP.mkdir(parents=True, exist_ok=True)
    for member in uv_members():
        if member.has_tests:
            basetemp = PYTEST_TMP / member.name
            runner.run(
                f"pytest: {member.name}",
                _uv_tool(member, "pytest", f"--basetemp={basetemp}"),
                member.path,
            )
        else:
            print(
                f"pytest: {member.name} has no tests/ folder or [tool.pytest.ini_options], skipped"
            )
    runner.run("pnpm test", _pnpm_script("test"))


def step_build(runner: Runner) -> None:
    out_dir = ROOT / "dist" / "python"
    for member in uv_members():
        if member.is_buildable:
            runner.run(
                f"uv build: {member.name}",
                [*uv_command(), "build", "--package", member.name, "--out-dir", str(out_dir)],
            )
    runner.run("pnpm build", _pnpm_script("build"))


def step_hooks(runner: Runner) -> None:
    for name, relative, args in HOOKS:
        script = ROOT / relative
        if script.is_file():
            runner.run(
                f"hook: {name}",
                [*uv_command(), "run", "--locked", "--all-packages", "python", str(script), *args],
            )
        else:
            print(f"hook: {name} not present yet ({relative}), skipped")


STEP_FUNCTIONS = {
    "install": step_install,
    "lint": step_lint,
    "typecheck": step_typecheck,
    "test": step_test,
    "build": step_build,
    "hooks": step_hooks,
}


def main(argv: Sequence[str]) -> int:
    steps = list(STEPS) if list(argv) == ["all"] else list(argv)
    unknown = [s for s in steps if s not in STEP_FUNCTIONS]
    if not steps or unknown:
        print(f"usage: run.py <step>... | all   (steps: {', '.join(STEPS)})", file=sys.stderr)
        return 2
    runner = Runner()
    for step in steps:
        STEP_FUNCTIONS[step](runner)
    if runner.failures:
        print("\nFAILED:\n  " + "\n  ".join(runner.failures), file=sys.stderr)
        return 1
    print(f"\nOK: {', '.join(steps)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
