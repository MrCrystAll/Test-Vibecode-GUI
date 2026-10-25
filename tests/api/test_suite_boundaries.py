# SPDX-License-Identifier: Apache-2.0
"""The suite is black-box: it must not import app or package code (TC-30 AC2, test plan T-30-2)."""

import ast
from pathlib import Path

import pytest

SUITE = Path(__file__).resolve().parent
# Top-level import names of every Python member under apps/ and packages/.
FORBIDDEN = {"studio_backend", "studio_config_schema", "studio_rlgym_adapter", "apps", "packages"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.ac("TC-30", 2)
def test_suite_imports_no_app_or_package_code() -> None:
    offenders = {
        str(p.relative_to(SUITE)): sorted(_imports(p) & FORBIDDEN)
        for p in SUITE.rglob("*.py")
        if ".venv" not in p.parts
    }

    assert {k: v for k, v in offenders.items() if v} == {}
