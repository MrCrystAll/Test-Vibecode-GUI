# SPDX-License-Identifier: Apache-2.0
"""Check a PR title, which becomes the squash-merge commit subject (TC-27, workflow.md "Commits").

    uv run --no-project python tools/ci/pr_title.py "feat(ui): add run list (TC-12)"

Rule: `<type>(<scope>)[!]: <summary> (TC-<n>)`, optionally followed by GitHub's ` (#<pr>)` when a
squash-merge subject is checked. Exits 1 with the reasons when the title does not match.
Standard library only.
"""

import re
import sys
from collections.abc import Sequence

TYPES = (
    "feat",
    "fix",
    "chore",
    "docs",
    "test",
    "refactor",
    "perf",
    "build",
    "ci",
    "style",
    "revert",
)
# workflow.md "Commits": keep the two lists in sync.
SCOPES = ("desktop", "ui", "backend", "adapter", "contract", "config", "ci", "docs")

_TITLE = re.compile(
    r"^(?P<type>[a-z]+)\((?P<scope>[a-z-]+)\)(?P<breaking>!)?: (?P<summary>.+?)"
    r" \((?P<ticket>TC-[1-9][0-9]*)\)(?: \(#[0-9]+\))?$"
)
EXAMPLE = "feat(ui): add run list (TC-12)"


def problems(title: str) -> list[str]:
    """Why `title` is not a valid PR title; empty when it is."""
    match = _TITLE.match(title)
    if match is None:
        return [f"expected `type(scope): summary (TC-n)`, e.g. `{EXAMPLE}`"]
    found = []
    if match["type"] not in TYPES:
        found.append(f"type {match['type']!r} is not one of {', '.join(TYPES)}")
    if match["scope"] not in SCOPES:
        found.append(f"scope {match['scope']!r} is not one of {', '.join(SCOPES)}")
    summary = match["summary"]
    if summary != summary.strip() or summary.endswith("."):
        found.append("summary must not start/end with spaces or end with a period")
    return found


def main(argv: Sequence[str]) -> int:
    if len(argv) != 1:
        print('usage: pr_title.py "<title>"', file=sys.stderr)
        return 2
    title = argv[0]
    found = problems(title)
    if found:
        print(f"PR title {title!r} is not a Conventional Commit for this repo:", file=sys.stderr)
        for problem in found:
            print(f"  - {problem}", file=sys.stderr)
        print("See docs/process/workflow.md (Commits).", file=sys.stderr)
        return 1
    print(f"PR title OK: {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
