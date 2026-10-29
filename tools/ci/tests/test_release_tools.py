# SPDX-License-Identifier: Apache-2.0
"""Self-tests for tools/ci/pr_title.py and tools/tag-prerelease.py (TC-27)."""

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from types import ModuleType

TOOLS = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pr_title = _load("pr_title", TOOLS / "ci" / "pr_title.py")
tag_prerelease = _load("tag_prerelease", TOOLS / "tag-prerelease.py")


class PrTitleTest(unittest.TestCase):
    def test_valid_titles(self) -> None:
        for title in (
            "feat(ui): add run list (TC-12)",
            "fix(backend): isolate the openapi test (TC-44)",
            "feat(contract)!: rename the run endpoints (TC-90)",
            "chore(ci): pipeline (TC-26) (#11)",  # squash-merge subject
        ):
            with self.subTest(title):
                self.assertEqual(pr_title.problems(title), [])

    def test_invalid_titles(self) -> None:
        for title, reason in (
            ("add run list", "expected"),
            ("feat: add run list (TC-12)", "expected"),  # scope is required
            ("feat(ui): add run list", "expected"),  # ticket is required
            ("feat(ui): add run list TC-12", "expected"),
            ("feat(ui) add run list (TC-12)", "expected"),
            ("feat(ui): add run list (TC-0)", "expected"),
            ("Feat(ui): add run list (TC-12)", "expected"),
            ("feature(ui): add run list (TC-12)", "type 'feature'"),
            ("docs(design): colour tokens (TC-1)", "scope 'design'"),
            ("feat(ui): add run list. (TC-12)", "period"),
        ):
            with self.subTest(title):
                found = pr_title.problems(title)
                self.assertTrue(found)
                self.assertIn(reason, " ".join(found))

    def test_ticketless_exemptions(self) -> None:
        for title in (
            "docs(process): branch protection on dev and main",
            "docs(adr): ADR-0007 something",
            "docs(product): roadmap risks (#21)",
        ):
            with self.subTest(title):
                self.assertEqual(pr_title.problems(title), [])
        self.assertEqual(pr_title.problems("release: v0.1.0", base="main"), [])

    def test_exemptions_are_narrow(self) -> None:
        for title, base in (
            ("docs(docs): roadmap wording", "dev"),  # other docs scopes still need a key
            ("docs(process): ends with a period.", "dev"),
            ("feat(process): something", "dev"),
            ("release: v0.1.0", "dev"),  # release titles only into main
            ("release: 0.1.0", "main"),
            ("feat(ui): no key into main", "main"),
        ):
            with self.subTest(title=title, base=base):
                self.assertTrue(pr_title.problems(title, base))

    def test_main_exit_codes(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pr_title.main(["feat(ui): add run list (TC-12)"]), 0)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(pr_title.main(["nope"]), 1)
        self.assertIn("workflow.md", err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pr_title.main([]), 2)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pr_title.main(["release: v0.1.0", "--base", "main"]), 0)


class NextTagTest(unittest.TestCase):
    """AC3: no tags yet, existing alphas, existing betas, mixed versions."""

    def test_no_tags_yet(self) -> None:
        self.assertEqual(tag_prerelease.next_tag("0.1.0", "alpha", []), "v0.1.0-alpha.1")
        self.assertEqual(tag_prerelease.next_tag("0.1.0", "beta", []), "v0.1.0-beta.1")

    def test_existing_alphas(self) -> None:
        tags = ["v0.1.0-alpha.1", "v0.1.0-alpha.2", "v0.1.0-alpha.10", "v0.1.0-alpha.9"]
        self.assertEqual(tag_prerelease.next_tag("0.1.0", "alpha", tags), "v0.1.0-alpha.11")

    def test_first_beta_after_alphas(self) -> None:
        tags = ["v0.1.0-alpha.1", "v0.1.0-alpha.16"]
        self.assertEqual(tag_prerelease.next_tag("0.1.0", "beta", tags), "v0.1.0-beta.1")

    def test_existing_betas(self) -> None:
        tags = ["v0.1.0-alpha.16", "v0.1.0-beta.1", "v0.1.0-beta.2"]
        self.assertEqual(tag_prerelease.next_tag("0.1.0", "beta", tags), "v0.1.0-beta.3")

    def test_mixed_versions_only_count_their_own_tags(self) -> None:
        tags = ["v0.1.0-alpha.16", "v0.2.0-alpha.1", "v0.1.0", "v0.10.0-alpha.7", "v1.0.0-alpha.3"]
        self.assertEqual(tag_prerelease.next_tag("0.2.0", "alpha", tags), "v0.2.0-alpha.2")
        self.assertEqual(tag_prerelease.next_tag("0.1.1", "alpha", tags), "v0.1.1-alpha.1")

    def test_ignores_malformed_tags(self) -> None:
        tags = ["v0.2.0-alpha.x", "v0.2.0-alpha.05", "v0.2.0-alpha.3-fix", "0.2.0-alpha.9"]
        self.assertEqual(tag_prerelease.next_tag("0.2.0", "alpha", tags), "v0.2.0-alpha.1")

    def test_refuses_alpha_after_beta(self) -> None:
        with self.assertRaisesRegex(tag_prerelease.TagError, "already has a beta"):
            tag_prerelease.next_tag("0.1.0", "alpha", ["v0.1.0-beta.1"])

    def test_refuses_pre_release_after_release(self) -> None:
        with self.assertRaisesRegex(tag_prerelease.TagError, "already released"):
            tag_prerelease.next_tag("0.1.0", "beta", ["v0.1.0-beta.2", "v0.1.0"])

    def test_rejects_bad_version_and_channel(self) -> None:
        for version, channel in (("0.2", "alpha"), ("v0.2.0", "alpha"), ("0.2.0", "rc")):
            with (
                self.subTest(version=version, channel=channel),
                self.assertRaises(tag_prerelease.TagError),
            ):
                tag_prerelease.next_tag(version, channel, [])


class FakeGit:
    """Answers git commands from a small in-memory repository and records the calls."""

    def __init__(
        self,
        branch: str = "dev",
        dirty: str = "",
        head: str = "a" * 40,
        upstream: str = "a" * 40,
        tags: str = "v0.1.0-alpha.1",
    ) -> None:
        self.answers = {
            ("rev-parse", "--abbrev-ref", "HEAD"): branch,
            ("status", "--porcelain"): dirty,
            ("rev-parse", "HEAD"): head,
            ("rev-parse", "origin/dev"): upstream,
            ("tag", "--list"): tags,
        }
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        self.calls.append(args)
        if args[:2] == ("log", "-1"):
            return "feat(ui): something (TC-1) (#1)"
        return self.answers.get(args, "")

    def ran(self, command: str) -> bool:
        return any(call[0] == command for call in self.calls)


class TagPrereleaseMainTest(unittest.TestCase):
    def _main(self, argv: list[str], git: FakeGit) -> tuple[int, str, str]:
        with (
            contextlib.redirect_stdout(io.StringIO()) as out,
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            code = tag_prerelease.main(argv, git=git)
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_prints_and_changes_nothing(self) -> None:
        git = FakeGit()
        code, out, _ = self._main(["--version", "0.1.0", "--channel", "alpha", "--dry-run"], git)

        self.assertEqual(code, 0)
        self.assertIn("would tag aaaaaaa", out)
        self.assertIn("v0.1.0-alpha.2", out)
        self.assertFalse(git.ran("tag") and any(c[:2] == ("tag", "--annotate") for c in git.calls))
        self.assertFalse(git.ran("push"))

    def test_creates_an_annotated_tag_and_pushes_only_with_push(self) -> None:
        git = FakeGit()
        code, out, _ = self._main(["--version", "0.1.0", "--channel", "alpha"], git)

        self.assertEqual(code, 0)
        self.assertIn(("tag", "--annotate", "v0.1.0-alpha.2"), [c[:3] for c in git.calls])
        self.assertFalse(git.ran("push"))
        self.assertIn("not pushed", out)

        git = FakeGit()
        self._main(["--version", "0.1.0", "--channel", "alpha", "--push"], git)
        self.assertIn(("push", "origin", "refs/tags/v0.1.0-alpha.2"), git.calls)

    def test_refuses_when_the_repository_is_not_ready(self) -> None:
        for git, reason in (
            (FakeGit(branch="feat/x"), "must run on dev"),
            (FakeGit(dirty=" M README.md"), "not clean"),
            (FakeGit(upstream="b" * 40), "pull first"),
        ):
            with self.subTest(reason):
                code, _, err = self._main(["--version", "0.1.0", "--channel", "alpha"], git)
                self.assertEqual(code, 1)
                self.assertIn(reason, err)
                self.assertFalse(any(c[:2] == ("tag", "--annotate") for c in git.calls))

    def test_fetches_before_comparing_with_origin(self) -> None:
        git = FakeGit()
        self._main(["--version", "0.1.0", "--channel", "alpha", "--dry-run"], git)

        fetch = git.calls.index(("fetch", "--quiet", "--tags", "origin", "dev"))
        self.assertLess(fetch, git.calls.index(("rev-parse", "origin/dev")))


if __name__ == "__main__":
    unittest.main()
