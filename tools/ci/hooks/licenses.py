# SPDX-License-Identifier: Apache-2.0
"""CI hook (TC-28): every npm and Python dependency, transitive and dev, has an allowed licence.

    uv run --locked --all-packages python tools/ci/hooks/licenses.py            # check
    uv run --locked --all-packages python tools/ci/hooks/licenses.py --list     # print all
    uv run --locked --all-packages python tools/ci/hooks/licenses.py --notices NOTICES.md

Run by tools/ci/run.py (`hooks` step) from the repository root, inside the uv workspace
environment, so the Python distributions seen here are exactly the locked workspace dependencies.
npm packages come from `pnpm -r licenses list --json`. The policy (allow-list and commented
exceptions) is tools/ci/licenses.toml. SPDX expressions are understood: `A OR B` needs one allowed
side, `A AND B` needs both.
"""

import argparse
import importlib.metadata as metadata
import json
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / "tools" / "ci" / "licenses.toml"
OWN_PREFIX = "studio-"  # our own workspace members are Apache-2.0 by definition
UNKNOWN = "UNKNOWN"

# Trove classifiers for packages without an SPDX `License-Expression` (older metadata).
# "BSD License" does not say which variant; BSD-2 and BSD-3 are both allowed, so the verdict holds.
CLASSIFIERS = {
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "ISC License (ISCL)": "ISC",
    "MIT License": "MIT",
    "MIT No Attribution License (MIT-0)": "MIT-0",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "The Unlicense (Unlicense)": "Unlicense",
    "zlib/libpng License": "Zlib",
}
_SPDX_ID = re.compile(r"^[A-Za-z0-9.+-]+$")
_LICENSE_FILE = re.compile(r"^(licen[cs]e|copying|notice)([.-].*)?$", re.IGNORECASE)


@dataclass(frozen=True)
class Package:
    ecosystem: str  # "npm" or "python"
    name: str
    version: str
    license: str
    license_files: tuple[Path, ...] = ()
    homepage: str = ""


@dataclass(frozen=True)
class Exception_:
    ecosystem: str
    package: str
    license: str
    reason: str


# --- SPDX expressions ----------------------------------------------------------------------------


def _tokens(expression: str) -> list[str]:
    return re.findall(r"\(|\)|[^\s()]+", expression)


def is_allowed(expression: str, allowed: Iterable[str]) -> bool:
    """Whether an SPDX expression is satisfied by the allow-list (OR: any side, AND: every side)."""
    allowed_set = set(allowed)
    tokens = _tokens(expression)
    position = 0

    def parse_or() -> bool:
        nonlocal position
        result = parse_and()
        while position < len(tokens) and tokens[position].upper() == "OR":
            position += 1
            right = parse_and()
            result = result or right
        return result

    def parse_and() -> bool:
        nonlocal position
        result = parse_atom()
        while position < len(tokens) and tokens[position].upper() == "AND":
            position += 1
            right = parse_atom()
            result = result and right
        return result

    def parse_atom() -> bool:
        nonlocal position
        if position >= len(tokens):
            raise ValueError(f"incomplete licence expression {expression!r}")
        token = tokens[position]
        position += 1
        if token == "(":
            result = parse_or()
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError(f"unbalanced licence expression {expression!r}")
            position += 1
            return result
        if position < len(tokens) and tokens[position].upper() == "WITH":
            exception = tokens[position + 1] if position + 1 < len(tokens) else ""
            position += 2
            return f"{token} WITH {exception}" in allowed_set
        return token in allowed_set

    try:
        result = parse_or()
    except ValueError:
        return False
    return result and position == len(tokens)


# --- collecting packages -------------------------------------------------------------------------


def python_license(meta: metadata.PackageMetadata) -> str:
    expression = meta.get("License-Expression")
    if expression:
        return str(expression).strip()
    declared = (meta.get("License") or "").strip()
    if declared and _SPDX_ID.match(declared):
        return declared
    for classifier in meta.get_all("Classifier") or []:
        if classifier.startswith("License :: "):
            name = classifier.rsplit(" :: ", 1)[-1]
            if name in CLASSIFIERS:
                return CLASSIFIERS[name]
    return UNKNOWN


def python_packages() -> list[Package]:
    found = {}
    for dist in metadata.distributions():
        meta = dist.metadata
        name = str(meta["Name"])
        if name.lower().startswith(OWN_PREFIX):
            continue
        home = str(meta.get("Home-page") or "")
        for url in meta.get_all("Project-URL") or []:
            home = home or str(url).split(",", 1)[-1].strip()
        files = tuple(
            Path(str(dist.locate_file(f)))
            for f in dist.files or []
            if ".dist-info" in str(f) and _LICENSE_FILE.match(Path(str(f)).name)
        )
        found[name.lower()] = Package(
            "python", name, str(meta["Version"]), python_license(meta), files, home
        )
    return sorted(found.values(), key=lambda p: p.name.lower())


def _pnpm() -> list[str]:
    pnpm = shutil.which("pnpm")
    if pnpm:
        return [pnpm]
    corepack = shutil.which("corepack")
    if corepack:
        return [corepack, "pnpm"]
    raise SystemExit("pnpm not found: install Node.js 24 and run `corepack enable`")


def npm_packages(listing: str | None = None) -> list[Package]:
    """Packages from `pnpm -r licenses list --json` (or from `listing`, its JSON output)."""
    if listing is None:
        listing = subprocess.run(  # noqa: S603 - fixed command
            [*_pnpm(), "-r", "licenses", "list", "--json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            encoding="utf-8",
        ).stdout
    found = {}
    for license_, entries in json.loads(listing or "{}").items():
        for entry in entries:
            if str(entry["name"]).startswith("@studio/"):
                continue
            paths = entry.get("paths") or []
            for version in entry.get("versions") or [""]:
                found[(entry["name"], version)] = Package(
                    "npm",
                    entry["name"],
                    version,
                    str(license_ or UNKNOWN),
                    _license_files_in(Path(paths[0])) if paths else (),
                    str(entry.get("homepage") or ""),
                )
    return sorted(found.values(), key=lambda p: (p.name, p.version))


# --- policy --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Policy:
    allowed: tuple[str, ...]
    exceptions: tuple[Exception_, ...]


def load_policy(path: Path = POLICY) -> Policy:
    with path.open("rb") as f:
        data = tomllib.load(f)
    exceptions = []
    for entry in data.get("exception", []):
        missing = [
            key for key in ("ecosystem", "package", "license", "reason") if not entry.get(key)
        ]
        if missing:
            raise SystemExit(f"{path}: exception {entry!r} lacks {', '.join(missing)}")
        exceptions.append(
            Exception_(entry["ecosystem"], entry["package"], entry["license"], entry["reason"])
        )
    return Policy(tuple(data["allowed"]), tuple(exceptions))


def violations(packages: Iterable[Package], policy: Policy) -> list[str]:
    excepted = {(e.ecosystem, e.package, e.license) for e in policy.exceptions}
    found = []
    for package in packages:
        if (package.ecosystem, package.name, package.license) in excepted:
            continue
        if not is_allowed(package.license, policy.allowed):
            found.append(
                f"{package.ecosystem}: {package.name}@{package.version} is licensed "
                f"{package.license!r}, which is not in the allow-list"
            )
    return found


def unused_exceptions(packages: Iterable[Package], policy: Policy) -> list[Exception_]:
    present = {(p.ecosystem, p.name, p.license) for p in packages}
    return [e for e in policy.exceptions if (e.ecosystem, e.package, e.license) not in present]


# --- notices -------------------------------------------------------------------------------------


def _license_files_in(folder: Path) -> tuple[Path, ...]:
    if not folder.is_dir():
        return ()
    return tuple(f for f in sorted(folder.iterdir()) if f.is_file() and _LICENSE_FILE.match(f.name))


def write_notices(packages: Iterable[Package], path: Path) -> None:
    lines = [
        "# Third-party notices",
        "",
        "rlgym-learn studio includes or depends on the following third-party software.",
        "Generated by `tools/ci/hooks/licenses.py --notices`; do not edit by hand.",
        "",
    ]
    for package in packages:
        lines += ["", f"## {package.name} {package.version} ({package.ecosystem})", ""]
        lines.append(f"License: {package.license}")
        if package.homepage:
            lines.append(f"Homepage: {package.homepage}")
        for file in package.license_files:
            text = file.read_text(encoding="utf-8", errors="replace").strip()
            lines += ["", "```text", text, "```"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


# --- entry point ---------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--list", action="store_true", help="print every package and licence")
    parser.add_argument("--notices", type=Path, help="write a third-party notices file here")
    args = parser.parse_args(argv)

    policy = load_policy()
    packages = [*python_packages(), *npm_packages()]
    if args.list:
        for package in packages:
            print(f"{package.ecosystem:6} {package.name}@{package.version}: {package.license}")
    if args.notices:
        write_notices(packages, args.notices)
        print(f"wrote {args.notices} ({len(packages)} packages)")
    for exception in unused_exceptions(packages, policy):
        print(
            f"warning: exception for {exception.ecosystem} {exception.package} "
            f"({exception.license}) no longer matches anything; remove it from {POLICY.name}"
        )
    found = violations(packages, policy)
    python_count = sum(p.ecosystem == "python" for p in packages)
    if found:
        print("\n".join(found), file=sys.stderr)
        print(
            f"licences: {len(found)} not allowed. Replace the dependency, or add a commented "
            f"exception to tools/ci/licenses.toml (docs/process/licensing.md).",
            file=sys.stderr,
        )
        return 1
    print(
        f"licences: OK ({python_count} Python + {len(packages) - python_count} npm packages, "
        "transitive and dev included)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
