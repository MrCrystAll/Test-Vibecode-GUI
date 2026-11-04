# SPDX-License-Identifier: Apache-2.0
"""CI hook (TC-33, QA strategy §5.6): the migration corpus is append-only.

    uv run --no-project python tools/ci/hooks/corpus-immutable.py [--base <ref>] [--root PATH]

Fails when a file under `packages/config-schema/tests/fixtures/<kind>/v<N>/` was modified, deleted,
renamed, copied over or had its type changed, compared with the merge base of HEAD and the base branch.
The working tree counts, so a local run also catches uncommitted edits. Adding a new sample is allowed.

Base branch: `--base`, else `origin/$GITHUB_BASE_REF` on a pull request, else `origin/dev`. On a push
to the base branch itself the merge base is HEAD, so nothing is compared. CI checks out the full
history (`fetch-depth: 0`) so the merge base exists; without it the hook fails rather than passing
silently.

Standard library only. Self-tests: tools/ci/tests/test_corpus_immutable.py.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[3]
CORPUS = "packages/config-schema/tests/fixtures"
SAMPLE = re.compile(rf"^{re.escape(CORPUS)}/[^/]+/v\d+/")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed git command
        ["git", *args],  # noqa: S607 - git on PATH
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"corpus-immutable: git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def default_base() -> str:
    branch = os.environ.get("GITHUB_BASE_REF") or "dev"
    return f"origin/{branch}"


def violations(root: Path, base: str) -> list[str]:
    """`<status> <path>` for every changed corpus sample that is not a pure addition."""
    merge_base = git(root, "merge-base", "HEAD", base).strip()
    # No --cached and no second commit: compare the merge base with the working tree.
    output = git(root, "diff", "--name-status", "-M", "-C", merge_base, "--", CORPUS)
    found = []
    for line in output.splitlines():
        status, *paths = line.split("\t")
        if status == "A":
            continue
        # A rename or copy lists the old path first: protected if either side is a sample.
        if any(SAMPLE.match(p) for p in paths):
            found.append(f"{status[0]} {' -> '.join(paths)}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=None, help="base branch ref (default: origin/$GITHUB_BASE_REF or origin/dev)")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    base = args.base or default_base()
    found = violations(args.root, base)
    if found:
        for item in found:
            print(f"corpus-immutable: {item}", file=sys.stderr)
        print(
            f"corpus-immutable: {len(found)} corpus sample(s) changed against {base}. The corpus is append-only:"
            " add a new sample instead of editing one (packages/config-schema/README.md).",
            file=sys.stderr,
        )
        return 1
    print(f"corpus-immutable: OK (no corpus sample changed against {base})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
