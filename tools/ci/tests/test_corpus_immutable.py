# SPDX-License-Identifier: Apache-2.0
"""Self-tests for tools/ci/hooks/corpus-immutable.py (TC-33, QA T-33-8): each throwaway git repo
gets a base branch with one corpus sample, then a feature branch modifies, deletes, renames or adds."""

import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "corpus_immutable", Path(__file__).resolve().parents[1] / "hooks" / "corpus-immutable.py"
)
assert _SPEC is not None and _SPEC.loader is not None  # noqa: S101
hook = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(hook)

SAMPLE = "packages/config-schema/tests/fixtures/project/v1/minimal.json"


class CorpusImmutableTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="corpus é ")
        self.root = Path(self._tmp.name)
        self.git("init", "-q", "-b", "dev")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("config", "core.autocrlf", "false")
        self.write(SAMPLE, '{"a": 1}\n')
        self.write("packages/config-schema/tests/fixtures/README.md", "notes\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.git("switch", "-q", "-c", "feature")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)  # noqa: S603,S607

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")

    def run_hook(self) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = hook.main(["--base", "dev", "--root", str(self.root)])
        return code, err.getvalue()

    def commit(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")

    def test_untouched_corpus_passes(self) -> None:
        self.assertEqual(self.run_hook()[0], 0)

    def test_adding_a_sample_passes(self) -> None:
        self.write("packages/config-schema/tests/fixtures/project/v2/new.json", '{"b": 2}\n')
        self.write("packages/config-schema/tests/fixtures/sample/v0/new.json", '{"c": 3}\n')
        self.commit()
        self.assertEqual(self.run_hook()[0], 0)

    def test_modifying_a_sample_fails(self) -> None:
        self.write(SAMPLE, '{"a": 2}\n')
        self.commit()
        code, err = self.run_hook()
        self.assertEqual(code, 1)
        self.assertIn(f"M {SAMPLE}", err)
        self.assertIn("append-only", err)

    def test_uncommitted_edit_fails(self) -> None:
        self.write(SAMPLE, '{"a": 3}\n')
        self.assertEqual(self.run_hook()[0], 1)

    def test_deleting_a_sample_fails(self) -> None:
        (self.root / SAMPLE).unlink()
        self.commit()
        code, err = self.run_hook()
        self.assertEqual(code, 1)
        self.assertIn(f"D {SAMPLE}", err)

    def test_renaming_a_sample_fails(self) -> None:
        self.git("mv", SAMPLE, SAMPLE.replace("minimal", "renamed"))
        self.commit()
        code, err = self.run_hook()
        self.assertEqual(code, 1)
        self.assertIn("R ", err)

    def test_files_outside_version_folders_are_free(self) -> None:
        self.write("packages/config-schema/tests/fixtures/README.md", "changed\n")
        self.commit()
        self.assertEqual(self.run_hook()[0], 0)

    def test_base_moving_ahead_is_not_a_change(self) -> None:
        """A sample added on dev after branching is not reported as deleted on the branch."""
        self.git("switch", "-q", "dev")
        self.write("packages/config-schema/tests/fixtures/project/v1/later.json", '{"d": 4}\n')
        self.commit()
        self.git("switch", "-q", "feature")
        self.assertEqual(self.run_hook()[0], 0)

    def test_unknown_base_fails_loudly(self) -> None:
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(io.StringIO()):
            hook.main(["--base", "origin/missing", "--root", str(self.root)])
        self.assertIn("merge-base", str(caught.exception.code))


if __name__ == "__main__":
    unittest.main()
