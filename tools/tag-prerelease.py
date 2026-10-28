# SPDX-License-Identifier: Apache-2.0
"""Tag the next pre-release of an epic on `dev` (TC-27, workflow.md "Versioning").

    uv run --no-project python tools/tag-prerelease.py --version 0.2.0 --channel alpha --dry-run
    uv run --no-project python tools/tag-prerelease.py --version 0.2.0 --channel alpha --push

Next K: one more than the highest existing `v<version>-<channel>.K` (1 if none). Refuses to run
unless the current branch is `dev`, the working tree is clean and HEAD equals `origin/dev` after a
fetch. Also refuses an alpha once a beta of that version exists, and any pre-release once the
release `v<version>` itself is tagged. Creates an annotated tag on HEAD; pushes it only with
`--push`. Standard library only.
"""

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence

CHANNELS = ("alpha", "beta")
BRANCH = "dev"
REMOTE = "origin"
_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")

Git = Callable[..., str]


class TagError(Exception):
    """The tag cannot or must not be created; the message says why."""


def run_git(*args: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed git commands
        ["git", *args],  # noqa: S607 - git on PATH
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TagError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _numbers(tags: Iterable[str], version: str, channel: str) -> list[int]:
    pattern = re.compile(rf"^v{re.escape(version)}-{channel}\.([1-9][0-9]*)$")
    return [int(m.group(1)) for tag in tags if (m := pattern.match(tag))]


def next_tag(version: str, channel: str, tags: Iterable[str]) -> str:
    """The tag to create, given every existing tag name."""
    if not _VERSION.match(version):
        raise TagError(f"--version must look like 0.2.0, got {version!r}")
    if channel not in CHANNELS:
        raise TagError(f"--channel must be one of {', '.join(CHANNELS)}, got {channel!r}")
    tags = list(tags)
    if f"v{version}" in tags:
        raise TagError(f"v{version} is already released; pre-releases come before the release")
    if channel == "alpha" and _numbers(tags, version, "beta"):
        raise TagError(f"v{version} already has a beta; stabilisation fixes are betas, not alphas")
    return f"v{version}-{channel}.{max(_numbers(tags, version, channel), default=0) + 1}"


def check_repository(git: Git) -> str:
    """Verify branch, clean tree and sync with the remote; return the HEAD commit."""
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != BRANCH:
        raise TagError(f"must run on {BRANCH}, current branch is {branch!r}")
    if git("status", "--porcelain"):
        raise TagError("working tree is not clean; commit or stash first")
    git("fetch", "--quiet", "--tags", REMOTE, BRANCH)
    head = git("rev-parse", "HEAD")
    upstream = git("rev-parse", f"{REMOTE}/{BRANCH}")
    if head != upstream:
        raise TagError(f"HEAD {head[:7]} is not {REMOTE}/{BRANCH} {upstream[:7]}; pull first")
    return head


def main(argv: Sequence[str] | None = None, git: Git = run_git) -> int:
    parser = argparse.ArgumentParser(
        prog="tag-prerelease", description=(__doc__ or "").splitlines()[0]
    )
    parser.add_argument("--version", required=True, help="epic version, e.g. 0.2.0")
    parser.add_argument("--channel", required=True, choices=CHANNELS)
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would happen, change nothing"
    )
    parser.add_argument("--push", action="store_true", help=f"push the new tag to {REMOTE}")
    args = parser.parse_args(argv)
    try:
        head = check_repository(git)
        tag = next_tag(args.version, args.channel, git("tag", "--list").splitlines())
        subject = git("log", "-1", "--format=%s", head)
        if args.dry_run:
            print(f"would tag {head[:7]} ({subject}) as {tag}")
            if args.push:
                print(f"would push {tag} to {REMOTE}")
            return 0
        git("tag", "--annotate", tag, "--message", f"{tag}: {subject}", head)
        print(f"tagged {head[:7]} as {tag}")
        if args.push:
            git("push", REMOTE, f"refs/tags/{tag}")
            print(f"pushed {tag} to {REMOTE}")
        else:
            print(f"not pushed; run `git push {REMOTE} refs/tags/{tag}` or rerun with --push")
    except TagError as exc:
        print(f"tag-prerelease: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
