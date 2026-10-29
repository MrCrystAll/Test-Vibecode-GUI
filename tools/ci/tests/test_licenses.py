# SPDX-License-Identifier: Apache-2.0
"""Self-tests for tools/ci/hooks/licenses.py (TC-28)."""

import email.message
import importlib.util
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "licenses", Path(__file__).resolve().parents[1] / "hooks" / "licenses.py"
)
assert _SPEC is not None and _SPEC.loader is not None
licenses = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(licenses)

ALLOWED = ("MIT", "Apache-2.0", "BSD-3-Clause", "ISC")


def _meta(**fields: object) -> email.message.Message:
    meta = email.message.Message()
    for key, value in fields.items():
        for item in value if isinstance(value, list) else [value]:
            meta[key.replace("_", "-")] = str(item)
    return meta


class ExpressionTest(unittest.TestCase):
    def test_single_ids(self) -> None:
        self.assertTrue(licenses.is_allowed("MIT", ALLOWED))
        self.assertFalse(licenses.is_allowed("GPL-3.0-only", ALLOWED))
        self.assertFalse(licenses.is_allowed("UNKNOWN", ALLOWED))
        self.assertFalse(licenses.is_allowed("mit", ALLOWED))  # SPDX ids are exact

    def test_or_needs_one_allowed_side(self) -> None:
        self.assertTrue(licenses.is_allowed("MIT OR GPL-3.0-only", ALLOWED))
        self.assertTrue(licenses.is_allowed("(GPL-2.0-only OR Apache-2.0)", ALLOWED))
        self.assertFalse(licenses.is_allowed("GPL-2.0-only OR AGPL-3.0-only", ALLOWED))

    def test_and_needs_every_side(self) -> None:
        self.assertTrue(licenses.is_allowed("(Apache-2.0 AND BSD-3-Clause)", ALLOWED))
        self.assertFalse(licenses.is_allowed("MIT AND GPL-3.0-only", ALLOWED))

    def test_precedence_and_nesting(self) -> None:
        # AND binds tighter than OR: MIT OR (GPL AND ISC)
        self.assertTrue(licenses.is_allowed("MIT OR GPL-3.0-only AND ISC", ALLOWED))
        self.assertFalse(licenses.is_allowed("(MIT OR ISC) AND GPL-3.0-only", ALLOWED))

    def test_with_exceptions_must_be_listed_whole(self) -> None:
        expression = "GPL-2.0-only WITH Classpath-exception-2.0"
        self.assertFalse(licenses.is_allowed(expression, ALLOWED))
        self.assertTrue(licenses.is_allowed(expression, (*ALLOWED, expression)))

    def test_malformed_expressions_are_not_allowed(self) -> None:
        for expression in ("(MIT", "MIT)", "MIT OR", "", "MIT ISC"):
            with self.subTest(expression):
                self.assertFalse(licenses.is_allowed(expression, ALLOWED))


class PythonLicenseTest(unittest.TestCase):
    def test_license_expression_wins(self) -> None:
        meta = _meta(License_Expression="BSD-3-Clause", License="Other")
        self.assertEqual(licenses.python_license(meta), "BSD-3-Clause")

    def test_spdx_like_license_field(self) -> None:
        self.assertEqual(licenses.python_license(_meta(License="MPL-2.0")), "MPL-2.0")

    def test_classifier_fallback(self) -> None:
        meta = _meta(
            License="Copyright (c) someone, all the long text here",
            Classifier=["Programming Language :: Python", "License :: OSI Approved :: MIT License"],
        )
        self.assertEqual(licenses.python_license(meta), "MIT")

    def test_unknown(self) -> None:
        self.assertEqual(licenses.python_license(_meta(Name="x")), licenses.UNKNOWN)


class NpmParsingTest(unittest.TestCase):
    def test_parses_pnpm_json_and_skips_our_packages(self) -> None:
        listing = json.dumps(
            {
                "MIT": [
                    {"name": "left-pad", "versions": ["1.0.0", "1.1.0"], "paths": []},
                    {"name": "@studio/contract", "versions": ["0.0.0"], "paths": []},
                ],
                "(MIT OR CC0-1.0)": [{"name": "type-fest", "versions": ["4.0.0"], "paths": []}],
            }
        )

        packages = licenses.npm_packages(listing)

        self.assertEqual(
            [(p.name, p.version, p.license) for p in packages],
            [
                ("left-pad", "1.0.0", "MIT"),
                ("left-pad", "1.1.0", "MIT"),
                ("type-fest", "4.0.0", "(MIT OR CC0-1.0)"),
            ],
        )


class PolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _policy(self, text: str) -> object:
        path = self.dir / "licenses.toml"
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return licenses.load_policy(path)

    def test_violation_names_the_package(self) -> None:
        policy = self._policy('allowed = ["MIT"]\n')
        packages = [
            licenses.Package("npm", "ok", "1.0.0", "MIT"),
            licenses.Package("python", "copyleft", "2.0", "GPL-3.0-only"),
        ]

        found = licenses.violations(packages, policy)

        self.assertEqual(len(found), 1)
        self.assertIn("copyleft@2.0", found[0])
        self.assertIn("GPL-3.0-only", found[0])

    def test_exception_covers_only_that_package_and_licence(self) -> None:
        policy = self._policy(
            """
            allowed = ["MIT"]
            [[exception]]
            ecosystem = "npm"
            package = "caniuse-lite"
            license = "CC-BY-4.0"
            reason = "data only"
            """
        )
        packages = [
            licenses.Package("npm", "caniuse-lite", "1.0.0", "CC-BY-4.0"),
            licenses.Package("npm", "caniuse-lite", "2.0.0", "GPL-3.0-only"),  # licence changed
            licenses.Package("npm", "other-data", "1.0.0", "CC-BY-4.0"),
            licenses.Package("python", "caniuse-lite", "1.0.0", "CC-BY-4.0"),
        ]

        found = licenses.violations(packages, policy)

        self.assertEqual(len(found), 3)
        self.assertFalse(
            any("caniuse-lite@1.0.0 is licensed 'CC-BY" in f and "npm" in f for f in found)
        )

    def test_exception_without_reason_is_rejected(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self._policy(
                """
                allowed = ["MIT"]
                [[exception]]
                ecosystem = "npm"
                package = "x"
                license = "GPL-3.0-only"
                """
            )
        self.assertIn("reason", str(raised.exception))

    def test_unused_exceptions_are_reported(self) -> None:
        policy = self._policy(
            """
            allowed = ["MIT"]
            [[exception]]
            ecosystem = "npm"
            package = "gone"
            license = "CC-BY-4.0"
            reason = "removed later"
            """
        )
        unused = licenses.unused_exceptions([], policy)
        self.assertEqual([e.package for e in unused], ["gone"])

    def test_repository_policy_is_valid(self) -> None:
        policy = licenses.load_policy()
        self.assertIn("Apache-2.0", policy.allowed)
        self.assertTrue(all(e.reason for e in policy.exceptions))


class NoticesTest(unittest.TestCase):
    def test_notices_include_licence_texts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            license_file = Path(tmp) / "LICENSE"
            license_file.write_text("Permission is hereby granted", encoding="utf-8")
            out = Path(tmp) / "NOTICES.md"
            licenses.write_notices(
                [licenses.Package("npm", "left-pad", "1.0.0", "MIT", (license_file,), "https://x")],
                out,
            )
            text = out.read_text(encoding="utf-8")

        self.assertIn("## left-pad 1.0.0 (npm)", text)
        self.assertIn("License: MIT", text)
        self.assertIn("Permission is hereby granted", text)


if __name__ == "__main__":
    unittest.main()
