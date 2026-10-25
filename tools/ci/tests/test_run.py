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

    def test_no_workspace_means_no_members(self) -> None:
        _write(self.root / "pyproject.toml", '[project]\nname = "solo"\n')

        self.assertEqual(run.uv_members(self.root), [])


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


if __name__ == "__main__":
    unittest.main()
