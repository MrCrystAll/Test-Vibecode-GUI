# SPDX-License-Identifier: Apache-2.0
"""Generate the published JSON Schemas (TC-32 AC4).

    uv run --package studio-config-schema generate-schemas           # rewrite schemas/
    uv run --package studio-config-schema generate-schemas --check   # exit 1 if schemas/ is stale

One file per file type and version: `schemas/<kind>.v<schemaVersion>.schema.json`, JSON Schema
2020-12 with a stable `$id`. A published file never changes once its version ships: a format change
means a new version, so a new file (and a migration, TC-33).
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from studio_config_schema.envelope import Envelope
from studio_config_schema.project import ProjectFile
from studio_config_schema.workspace import AppSettings, WorkspaceMarker

DIALECT = "https://json-schema.org/draft/2020-12/schema"
ID_BASE = "https://raw.githubusercontent.com/MrCrystAll/Test-Vibecode-GUI/main/packages/config-schema/schemas/"
SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
COMMAND = "uv run --package studio-config-schema generate-schemas"

MODELS: tuple[type[Envelope], ...] = (ProjectFile, WorkspaceMarker, AppSettings)


def file_name(model: type[Envelope]) -> str:
    return f"{model.KIND}.v{model.SCHEMA_VERSION}.schema.json"


def schema_for(model: type[Envelope]) -> dict[str, Any]:
    body = model.model_json_schema(by_alias=True, mode="validation")
    # pydantic derives property titles from Python names ("Createdat"): noise, so drop them.
    for prop in body.get("properties", {}).values():
        prop.pop("title", None)
    return {"$schema": DIALECT, "$id": ID_BASE + file_name(model), **body}


def render(model: type[Envelope]) -> str:
    return json.dumps(schema_for(model), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def expected_files() -> dict[str, str]:
    return {file_name(model): render(model) for model in MODELS}


def stale_files(directory: Path = SCHEMAS_DIR) -> list[str]:
    """Names of the schema files that are missing or differ from what the models generate."""
    stale = []
    for name, text in expected_files().items():
        target = directory / name
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            stale.append(name)
    return stale


def write(directory: Path = SCHEMAS_DIR) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in expected_files().items():
        (directory / name).write_bytes(text.encode("utf-8"))
    return sorted(expected_files())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="fail if a committed schema is stale")
    parser.add_argument(
        "--out", type=Path, default=SCHEMAS_DIR, help="output folder (default: schemas/)"
    )
    args = parser.parse_args(argv)
    if args.check:
        stale = stale_files(args.out)
        if stale:
            print(f"Stale JSON Schema(s): {', '.join(stale)}. Run: {COMMAND}", file=sys.stderr)
            return 1
        print(f"JSON Schemas up to date ({len(MODELS)} file(s)).")
        return 0
    for name in write(args.out):
        print(f"wrote {args.out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
