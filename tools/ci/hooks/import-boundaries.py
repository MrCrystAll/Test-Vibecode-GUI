# SPDX-License-Identifier: Apache-2.0
"""Import-boundary check (TC-25): CLAUDE.md rules 1 and 3, ADR-0001, ADR-0004 section 8.

    uv run --no-project python tools/ci/hooks/import-boundaries.py [--root PATH]

Prints one line per violation (`path:line: RULE message`) and exits 1 if there are any.

Python (static, with `ast`; nothing needs to be installed or importable):
  PY-HEAVY            torch, rlgym, rlgym_learn, rlgym_learn_algos, wandb and mlflow are imported
                      only by `studio_rlgym_adapter.runner` (owner decision: no torch in the API).
  PY-PACKAGE-APP      nothing under packages/ imports an app module (ADR-0001).
  PY-BACKEND-ADAPTER  apps/backend imports only the adapter's `host` and `protocol` (ADR-0004 s. 1).
  PY-HOST-RUNNER      the adapter's host side never imports its runner side.
  PY-RUNNER-HOST      the adapter's runner side never imports its host side.
  PY-PROTOCOL-STDLIB  `studio_rlgym_adapter.protocol` imports the standard library only.
TypeScript / JavaScript (import, export-from, dynamic import() and require() specifiers):
  TS-PACKAGE-APP      nothing under packages/ imports from apps/ (by relative path or package name).
  TS-APP-APP          no app imports another app; apps talk only through the HTTP/WS contract.

Standard library only, so it runs before anything is installed. Self-tests: tools/ci/tests.
"""

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOTS = ("apps", "packages", "tests")
TS_ROOTS = ("apps", "packages")
TS_SUFFIXES = {".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs"}
SKIPPED_DIRS = {
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "out",
    "release",
    "coverage",
    ".angular",
}

HEAVY = {"torch", "rlgym", "rlgym_learn", "rlgym_learn_algos", "wandb", "mlflow"}
ADAPTER = "studio_rlgym_adapter"
HOST = f"{ADAPTER}.host"
RUNNER = f"{ADAPTER}.runner"
PROTOCOL = f"{ADAPTER}.protocol"


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {self.message}"


def _walk(root: Path, top_dirs: tuple[str, ...], suffixes: set[str]) -> Iterator[Path]:
    for top in top_dirs:
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            rel_parts = path.relative_to(root).parts
            if any(part in SKIPPED_DIRS for part in rel_parts[:-1]):
                continue
            if path.is_file() and path.suffix in suffixes:
                yield path


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _within(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


# --- Python -------------------------------------------------------------------------------------


def _module_name(root: Path, path: Path) -> str | None:
    """Dotted module name for a file in a src layout (`.../src/pkg/mod.py`), else None."""
    parts = path.relative_to(root).with_suffix("").parts
    if "src" not in parts:
        return None
    dotted = list(parts[parts.index("src") + 1 :])
    if dotted and dotted[-1] == "__init__":
        dotted.pop()
    return ".".join(dotted) or None


def _resolve_relative(
    module: str | None, is_package: bool, level: int, target: str | None
) -> str | None:
    if module is None:
        return None
    package = module.split(".") if is_package else module.split(".")[:-1]
    if level - 1 > len(package):
        return None
    base = package[: len(package) - (level - 1)]
    return ".".join([*base, target] if target else base) or None


def python_imports(
    source: str, module: str | None = None, is_package: bool = False
) -> list[tuple[str, int]]:
    """(dotted name, line) for every import in `source`, incl. constant import_module/__import__.

    `from a import b` yields `a.b` (b may be a submodule); relative ones resolve against `module`.
    """
    found: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (
                node.module
                if node.level == 0
                else _resolve_relative(module, is_package, node.level, node.module)
            )
            if base is None:
                continue
            for alias in node.names:
                found.append((base if alias.name == "*" else f"{base}.{alias.name}", node.lineno))
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            first = node.args[0]
            is_import_call = name in {"__import__", "import_module"}
            target = first.value if isinstance(first, ast.Constant) else None
            if is_import_call and isinstance(target, str) and not target.startswith("."):
                found.append((target, node.lineno))
    return found


def _app_python_modules(root: Path) -> set[str]:
    """Top-level import names of the Python apps (apps/<app>/src/<name>/), plus `apps` itself."""
    names = {"apps"}
    for init in root.glob("apps/*/src/*/__init__.py"):
        names.add(init.parent.name)
    return names


def _python_rules(
    rel: str, module: str | None, name: str, app_modules: set[str]
) -> list[tuple[str, str]]:
    """(rule, message) for each rule that importing `name` breaks in file `rel`."""
    top = name.split(".")[0]
    in_runner = module is not None and _within(module, RUNNER)
    in_host = module is not None and _within(module, HOST)
    in_protocol = module is not None and _within(module, PROTOCOL)
    broken: list[tuple[str, str]] = []
    if top in HEAVY and not in_runner:
        broken.append(("PY-HEAVY", f"only {RUNNER} may import {top}"))
    if rel.startswith("packages/") and top in app_modules:
        broken.append(("PY-PACKAGE-APP", "packages never import app modules"))
    backend_may_use = _within(name, HOST) or _within(name, PROTOCOL)
    if rel.startswith("apps/backend/") and top == ADAPTER and not backend_may_use:
        broken.append(("PY-BACKEND-ADAPTER", f"the backend may use only {HOST} and {PROTOCOL}"))
    if in_host and _within(name, RUNNER):
        broken.append(("PY-HOST-RUNNER", "the host side never imports the runner side"))
    if in_runner and _within(name, HOST):
        broken.append(("PY-RUNNER-HOST", "the runner side never imports the host side"))
    if in_protocol and top not in sys.stdlib_module_names and not _within(name, PROTOCOL):
        broken.append(("PY-PROTOCOL-STDLIB", f"{PROTOCOL} may import the stdlib only"))
    return broken


def check_python(root: Path) -> list[Violation]:
    app_modules = _app_python_modules(root)
    violations: list[Violation] = []
    for path in _walk(root, PYTHON_ROOTS, {".py"}):
        rel = _rel(root, path)
        module = _module_name(root, path)
        source = path.read_text(encoding="utf-8")
        try:
            imports = python_imports(source, module, path.name == "__init__.py")
        except SyntaxError as exc:
            violations.append(
                Violation(rel, exc.lineno or 0, "PY-SYNTAX", f"cannot parse: {exc.msg}")
            )
            continue
        for name, line in imports:
            for rule, why in _python_rules(rel, module, name, app_modules):
                violations.append(Violation(rel, line, rule, f"imports '{name}'; {why}"))
    return violations


# --- TypeScript / JavaScript --------------------------------------------------------------------

_SPECIFIER_PATTERNS = (
    re.compile(r"""\b(?:import|export)\b[^'"`;]*?\bfrom\s*(['"])(?P<spec>[^'"\n]+)\1"""),
    re.compile(r"""\bimport\s*(['"])(?P<spec>[^'"\n]+)\1"""),
    re.compile(r"""\bimport\s*\(\s*(['"])(?P<spec>[^'"\n]+)\1"""),
    re.compile(r"""\brequire\s*\(\s*(['"])(?P<spec>[^'"\n]+)\1"""),
)


def strip_comments(source: str) -> str:
    """Blank out // and /* */ comments, keeping strings and newlines (line numbers)."""
    out: list[str] = []
    i, n = 0, len(source)
    quote: str | None = None
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if quote:
            out.append(ch)
            if ch == "\\" and nxt:
                out.append(nxt)
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
        elif ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
        elif ch == "/" and nxt == "/":
            while i < n and source[i] != "\n":
                out.append(" ")
                i += 1
        elif ch == "/" and nxt == "*":
            end = source.find("*/", i + 2)
            end = n if end == -1 else end + 2
            out.extend("\n" if c == "\n" else " " for c in source[i:end])
            i = end
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def ts_specifiers(source: str) -> list[tuple[str, int]]:
    """(specifier, line) for every static or dynamic import / require in a TS or JS source."""
    code = strip_comments(source)
    found: set[tuple[int, str]] = set()
    for pattern in _SPECIFIER_PATTERNS:
        for match in pattern.finditer(code):
            start = match.start("spec")
            found.add((start, match.group("spec")))
    return [(spec, code.count("\n", 0, start) + 1) for start, spec in sorted(found)]


def _zone(root: Path, path: Path) -> tuple[str, str] | None:
    """('apps' | 'packages', folder name) for a path inside one of them, else None."""
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return None
    if len(parts) >= 2 and parts[0] in TS_ROOTS:
        return parts[0], parts[1]
    return None


def _workspace_packages(root: Path) -> dict[str, Path]:
    """package.json `name` -> folder, for every app and package."""
    names: dict[str, Path] = {}
    for manifest in sorted(
        [*root.glob("apps/*/package.json"), *root.glob("packages/*/package.json")]
    ):
        name = json.loads(manifest.read_text(encoding="utf-8")).get("name")
        if isinstance(name, str):
            names[name] = manifest.parent
    return names


def _package_name(specifier: str) -> str:
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") else parts[0]


def check_typescript(root: Path) -> list[Violation]:
    workspace = _workspace_packages(root)
    violations: list[Violation] = []
    for path in _walk(root, TS_ROOTS, TS_SUFFIXES):
        source_zone = _zone(root, path)
        if source_zone is None:
            continue
        for spec, line in ts_specifiers(path.read_text(encoding="utf-8")):
            if spec.startswith("."):
                target = _zone(root, path.parent / spec)
            elif _package_name(spec) in workspace:
                target = _zone(root, workspace[_package_name(spec)])
            else:
                continue
            if target is None or target[0] != "apps" or target == source_zone:
                continue
            if source_zone[0] == "packages":
                rule, why = "TS-PACKAGE-APP", "packages never import apps"
            else:
                rule, why = (
                    "TS-APP-APP",
                    "apps talk to each other only through the HTTP/WS contract",
                )
            violations.append(
                Violation(
                    _rel(root, path), line, rule, f"imports '{spec}' (apps/{target[1]}); {why}"
                )
            )
    return violations


def check(root: Path) -> list[Violation]:
    return sorted([*check_python(root), *check_typescript(root)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT, help="repository root (default: this repo)"
    )
    args = parser.parse_args(argv)
    violations = check(args.root)
    for violation in violations:
        print(violation)
    if violations:
        print(f"import-boundaries: {len(violations)} violation(s)", file=sys.stderr)
        return 1
    print("import-boundaries: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
