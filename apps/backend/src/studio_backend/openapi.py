# SPDX-License-Identifier: Apache-2.0
"""Export the OpenAPI schema into packages/contract/openapi.json (TC-18, ADR-0006).

    uv run --package studio-backend export-openapi           # rewrite the committed schema
    uv run --package studio-backend export-openapi --check   # exit 1 if it is out of date

The output is deterministic: UTF-8, LF, keys sorted, 2-space indent, trailing newline.
`info.version` is the contract version (API_VERSION), never the app version, so the file only
changes when the contract does.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from studio_backend.app import create_app

CONTRACT_FILE = Path("packages") / "contract" / "openapi.json"


def build_schema() -> dict[str, Any]:
    return create_app().openapi()


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def find_repo_root(start: Path) -> Path:
    """The nearest folder at or above `start` holding packages/contract/."""
    for folder in (start, *start.parents):
        if (folder / CONTRACT_FILE.parent).is_dir():
            return folder
    raise SystemExit(f"{CONTRACT_FILE.parent.as_posix()}/ not found above {start}; use --output")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="export-openapi", description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, help=f"default: <repo>/{CONTRACT_FILE.as_posix()}")
    parser.add_argument(
        "--check", action="store_true", help="compare with the file and write nothing"
    )
    args = parser.parse_args(argv)
    output: Path = args.output or find_repo_root(Path.cwd()) / CONTRACT_FILE
    expected = render(build_schema())

    if args.check:
        current = output.read_text(encoding="utf-8") if output.is_file() else None
        if current != expected:
            print(
                f"{output} is out of date with the backend routes.\n"
                "Run `uv run --package studio-backend export-openapi` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{output} is up to date.")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(expected.encode("utf-8"))  # bytes: no CRLF translation on Windows
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
