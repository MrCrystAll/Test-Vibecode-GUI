# SPDX-License-Identifier: Apache-2.0
"""CI hook (ADR-0006 drift check): the committed contract must match the code.

1. TC-18: packages/contract/openapi.json matches the backend routes (`export-openapi --check`).
2. TC-22: the generated TypeScript types match openapi.json
   (`pnpm --filter @studio/contract generate`, then `git diff --exit-code` on the generated folder).

Run by tools/ci/run.py (`hooks` step) from the repository root.
"""

import shutil
import subprocess
import sys

GENERATED = "packages/contract/src/generated"


def _pnpm() -> list[str]:
    pnpm = shutil.which("pnpm")
    if pnpm:
        return [pnpm]
    corepack = shutil.which("corepack")
    if corepack:
        return [corepack, "pnpm"]
    raise SystemExit("pnpm not found: install Node.js 24 and run `corepack enable`")


def _run(command: list[str]) -> int:
    return subprocess.run(command, check=False).returncode  # noqa: S603 - fixed commands


def main() -> int:
    export = ["uv", "run", "--locked", "--package", "studio-backend", "export-openapi", "--check"]
    if _run(export) != 0:
        return 1
    if _run([*_pnpm(), "--filter", "@studio/contract", "run", "generate"]) != 0:
        return 1
    if _run(["git", "diff", "--exit-code", "--", GENERATED]) != 0:
        print(
            f"{GENERATED} is out of date with openapi.json.\n"
            "Run `pnpm --filter @studio/contract generate` and commit the result.",
            file=sys.stderr,
        )
        return 1
    print(f"{GENERATED} is up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
