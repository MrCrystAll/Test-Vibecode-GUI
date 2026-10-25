# SPDX-License-Identifier: Apache-2.0
"""Self-tests for tools/ci/run.py (stdlib unittest, so they run before anything is installed)."""

import contextlib
import importlib.util
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "ci_run", Path(__file__).resolve().parents[1] / "run.py"
)
assert _SPEC is not None and _SPEC.loader is not None
run = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


class UvMembersTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_discovers_tools_per_member(self) -> None:
        _write(
            self.root / "pyproject.toml",
            """
            [tool.uv.workspace]
            members = ["apps/*", "packages/lib"]
            """,
        )
        _write(
            self.root / "apps/api/pyproject.toml",
            """
            [project]
            name = "api"
            [build-system]
            requires = ["uv_build"]
            [tool.ruff]
            line-length = 100
            [tool.mypy]
            strict = true
            """,
        )
        (self.root / "apps/api/tests").mkdir()
        _write(self.root / "packages/lib/pyproject.toml", '[project]\nname = "lib"\n')
        (self.root / "apps/not-a-member").mkdir(parents=True)  # matched by the glob, no manifest

        members = {m.name: m for m in run.uv_members(self.root)}

        self.assertEqual(set(members), {"api", "lib"})
        api, lib = members["api"], members["lib"]
        self.assertTrue(api.has_ruff and api.has_mypy and api.has_tests and api.is_buildable)
        self.assertFalse(lib.has_ruff or lib.has_mypy or lib.has_tests or lib.is_buildable)

    def test_pytest_config_without_tests_folder_counts_as_tests(self) -> None:
        # QA's tests/api keeps test files at the member root (TC-30); it must not be skipped.
        _write(self.root / "pyproject.toml", '[tool.uv.workspace]\nmembers = ["suite"]\n')
        _write(
            self.root / "suite/pyproject.toml",
            """
            [project]
            name = "suite"
            [tool.pytest.ini_options]
            testpaths = ["."]
            """,
        )

        (suite,) = run.uv_members(self.root)

        self.assertTrue(suite.has_tests)

    def test_no_workspace_means_no_members(self) -> None:
        _write(self.root / "pyproject.toml", '[project]\nname = "solo"\n')

        self.assertEqual(run.uv_members(self.root), [])


class _RecordingRunner(run.Runner):
    def __init__(self) -> None:
        super().__init__()
        self.titles: list[str] = []
        self.commands: list[list[str]] = []

    def run(self, title, command, cwd=run.ROOT):  # type: ignore[no-untyped-def]
        self.titles.append(title)
        self.commands.append(list(command))


class StepTestTest(unittest.TestCase):
    def test_members_without_tests_are_reported_as_skipped(self) -> None:
        members = [
            run.UvMember("with-tests", run.ROOT, False, False, True, False),
            run.UvMember("no-tests", run.ROOT, False, False, False, False),
        ]
        runner = _RecordingRunner()
        original = run.uv_members
        run.uv_members = lambda root=run.ROOT: members
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                run.step_test(runner)
        finally:
            run.uv_members = original

        self.assertIn("pytest: with-tests", runner.titles)
        self.assertNotIn("pytest: no-tests", runner.titles)
        self.assertIn("pytest: no-tests has no tests/ folder", out.getvalue())
        pytest_command = runner.commands[runner.titles.index("pytest: with-tests")]
        self.assertIn(f"--basetemp={run.PYTEST_TMP / 'with-tests'}", pytest_command)


class MainTest(unittest.TestCase):
    def test_unknown_step_is_a_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(run.main(["deploy"]), 2)
        self.assertIn("usage", err.getvalue())

    def test_no_step_is_a_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run.main([]), 2)

    def test_real_repository_members_are_found(self) -> None:
        names = {m.name for m in run.uv_members()}

        self.assertIn("studio-config-schema", names)
        self.assertIn("studio-rlgym-adapter", names)

    def test_real_api_suite_runs_its_tests(self) -> None:
        members = {m.name: m for m in run.uv_members()}

        self.assertTrue(members["studio-api-tests"].has_tests)

    def test_hook_scripts_live_in_the_repository(self) -> None:
        for name, relative, _args in run.HOOKS:
            with self.subTest(name):
                self.assertFalse(Path(relative).is_absolute())
        self.assertTrue((run.ROOT / "tests/fixtures/workspaces/generate.py").is_file())


if __name__ == "__main__":
    unittest.main()
