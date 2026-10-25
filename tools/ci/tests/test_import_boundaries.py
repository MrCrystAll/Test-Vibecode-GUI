# SPDX-License-Identifier: Apache-2.0
"""Self-tests for tools/ci/hooks/import-boundaries.py (TC-25 AC3): every rule catches a violating
fixture and accepts its clean counterpart. Each test builds a throwaway repo tree in a temp
folder."""

import contextlib
import importlib.util
import io
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "import_boundaries", Path(__file__).resolve().parents[1] / "hooks" / "import-boundaries.py"
)
assert _SPEC is not None and _SPEC.loader is not None  # noqa: S101
boundaries = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(boundaries)

ADAPTER_SRC = "packages/rlgym-adapter/src/studio_rlgym_adapter"
BACKEND_SRC = "apps/backend/src/studio_backend"


class _RepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # Minimal workspace: a Python app, the adapter's three sides, two TS apps and a TS package.
        self.write(f"{BACKEND_SRC}/__init__.py", "")
        for side in ("", "/host", "/runner", "/protocol"):
            self.write(f"{ADAPTER_SRC}{side}/__init__.py", "")
        self.write("apps/ui/package.json", json.dumps({"name": "@studio/ui"}))
        self.write("apps/desktop/package.json", json.dumps({"name": "@studio/desktop"}))
        self.write("packages/contract/package.json", json.dumps({"name": "@studio/contract"}))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, content: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")

    def rules(self) -> list[tuple[str, str, int]]:
        return [(v.rule, v.path, v.line) for v in boundaries.check(self.root)]


class CleanTreeTest(_RepoTestCase):
    def test_allowed_imports_pass(self) -> None:
        self.write(
            f"{ADAPTER_SRC}/runner/train.py",
            "import torch\nfrom rlgym_learn import Learner\nfrom ..protocol import events\n",
        )
        self.write(
            f"{ADAPTER_SRC}/host/launch.py",
            "import json\nfrom studio_rlgym_adapter.protocol import events\n",
        )
        self.write(
            f"{ADAPTER_SRC}/protocol/events.py",
            "from __future__ import annotations\nimport json\nfrom . import base\n",
        )
        self.write(
            f"{BACKEND_SRC}/runs.py",
            "import fastapi\n"
            "from studio_rlgym_adapter.host import launch\n"
            "from studio_rlgym_adapter import protocol\n",
        )
        self.write(
            "apps/ui/src/main.ts",
            "import { Api } from '@studio/contract';\nimport { x } from './app/x';\n",
        )
        self.write(
            "apps/desktop/src/main.ts",
            "import { app } from 'electron';\n"
            "const c = require('../../../packages/contract/index.js');\n",
        )
        self.assertEqual(self.rules(), [])

    def test_cli_exit_codes(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(boundaries.main(["--root", str(self.root)]), 0)
        self.write("packages/config-schema/src/studio_config_schema/x.py", "import torch\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(boundaries.main(["--root", str(self.root)]), 1)
        self.assertIn(
            "packages/config-schema/src/studio_config_schema/x.py:1: PY-HEAVY", out.getvalue()
        )

    def test_the_real_repository_passes(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(boundaries.main([]), 0)


class PythonRulesTest(_RepoTestCase):
    def test_heavy_import_outside_runner(self) -> None:
        self.write(f"{BACKEND_SRC}/a.py", "import torch.nn\n")
        self.write(f"{ADAPTER_SRC}/host/b.py", "\n\nfrom rlgym_learn_algos.ppo import PPO\n")
        self.write("tests/api/test_c.py", "import importlib\nimportlib.import_module('wandb')\n")
        self.write(
            "packages/config-schema/src/studio_config_schema/d.py", "x = __import__('rlgym')\n"
        )
        self.assertEqual(
            sorted(self.rules()),
            [
                ("PY-HEAVY", f"{BACKEND_SRC}/a.py", 1),
                ("PY-HEAVY", "packages/config-schema/src/studio_config_schema/d.py", 1),
                ("PY-HEAVY", f"{ADAPTER_SRC}/host/b.py", 3),
                ("PY-HEAVY", "tests/api/test_c.py", 2),
            ],
        )

    def test_package_imports_app(self) -> None:
        self.write(
            "packages/config-schema/src/studio_config_schema/a.py",
            "from studio_backend.settings import Settings\n",
        )
        self.write("packages/config-schema/tests/test_b.py", "import apps.backend\n")
        self.assertEqual(
            sorted(self.rules()),
            [
                ("PY-PACKAGE-APP", "packages/config-schema/src/studio_config_schema/a.py", 1),
                ("PY-PACKAGE-APP", "packages/config-schema/tests/test_b.py", 1),
            ],
        )

    def test_backend_imports_adapter_internals(self) -> None:
        self.write(f"{BACKEND_SRC}/a.py", "from studio_rlgym_adapter import runner\n")
        self.write(f"{BACKEND_SRC}/b.py", "import studio_rlgym_adapter\n")
        self.write(f"{BACKEND_SRC}/c.py", "from studio_rlgym_adapter.runner.fake import main\n")
        self.assertEqual(
            sorted(self.rules()),
            [
                ("PY-BACKEND-ADAPTER", f"{BACKEND_SRC}/a.py", 1),
                ("PY-BACKEND-ADAPTER", f"{BACKEND_SRC}/b.py", 1),
                ("PY-BACKEND-ADAPTER", f"{BACKEND_SRC}/c.py", 1),
            ],
        )

    def test_host_imports_runner(self) -> None:
        self.write(f"{ADAPTER_SRC}/host/a.py", "from ..runner import train\n")
        self.write(
            f"{ADAPTER_SRC}/host/__init__.py", "from studio_rlgym_adapter.runner import compat\n"
        )
        self.assertEqual(
            sorted(self.rules()),
            [
                ("PY-HOST-RUNNER", f"{ADAPTER_SRC}/host/__init__.py", 1),
                ("PY-HOST-RUNNER", f"{ADAPTER_SRC}/host/a.py", 1),
            ],
        )

    def test_runner_imports_host(self) -> None:
        self.write(f"{ADAPTER_SRC}/runner/compat/v2.py", "from ...host import paths\n")
        self.assertEqual(
            self.rules(), [("PY-RUNNER-HOST", f"{ADAPTER_SRC}/runner/compat/v2.py", 1)]
        )

    def test_protocol_imports_non_stdlib(self) -> None:
        self.write(f"{ADAPTER_SRC}/protocol/a.py", "import json\nimport pydantic\n")
        self.write(f"{ADAPTER_SRC}/protocol/b.py", "from ..host import paths\n")
        self.assertEqual(
            sorted(self.rules()),
            [
                ("PY-PROTOCOL-STDLIB", f"{ADAPTER_SRC}/protocol/a.py", 2),
                ("PY-PROTOCOL-STDLIB", f"{ADAPTER_SRC}/protocol/b.py", 1),
            ],
        )


class TypeScriptRulesTest(_RepoTestCase):
    def test_package_imports_app(self) -> None:
        self.write(
            "packages/contract/src/a.ts",
            "import { Shell } from '../../../apps/ui/src/app/shell';\n",
        )
        self.write("packages/contract/src/b.ts", "export * from '@studio/desktop/preload';\n")
        self.assertEqual(
            sorted(self.rules()),
            [
                ("TS-PACKAGE-APP", "packages/contract/src/a.ts", 1),
                ("TS-PACKAGE-APP", "packages/contract/src/b.ts", 1),
            ],
        )

    def test_ui_and_desktop_import_each_other(self) -> None:
        self.write("apps/ui/src/a.ts", "import {\n  ipc,\n} from '@studio/desktop';\n")
        self.write("apps/ui/src/b.ts", "const m = await import('../../backend/openapi.json');\n")
        self.write("apps/desktop/src/c.cjs", "const ui = require('../../ui/src/main');\n")
        self.write("apps/desktop/src/d.mts", "import '@studio/ui/styles';\n")
        self.assertEqual(
            sorted(self.rules()),
            [
                ("TS-APP-APP", "apps/desktop/src/c.cjs", 1),
                ("TS-APP-APP", "apps/desktop/src/d.mts", 1),
                ("TS-APP-APP", "apps/ui/src/a.ts", 3),
                ("TS-APP-APP", "apps/ui/src/b.ts", 1),
            ],
        )

    def test_comments_build_output_and_node_modules_are_ignored(self) -> None:
        self.write(
            "apps/ui/src/a.ts",
            "// import x from '@studio/desktop';\n/* require('../../desktop/x') */\nconst url = 'http://x//y';\n",
        )
        self.write("apps/ui/dist/main.js", "require('@studio/desktop');\n")
        self.write(
            "apps/ui/node_modules/@studio/desktop/index.js", "require('../../../../ui/src/x');\n"
        )
        self.assertEqual(self.rules(), [])


class HelpersTest(unittest.TestCase):
    def test_strip_comments_keeps_strings_and_lines(self) -> None:
        source = "a = '// not a comment';\n/* one\ntwo */ b = \"/* nor this */\"; // gone\n"
        stripped = boundaries.strip_comments(source)
        self.assertEqual(stripped.count("\n"), source.count("\n"))
        self.assertIn("'// not a comment'", stripped)
        self.assertIn('"/* nor this */"', stripped)
        self.assertNotIn("gone", stripped)
        self.assertNotIn("two", stripped)


if __name__ == "__main__":
    unittest.main()
