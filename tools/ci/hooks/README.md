# tools/ci/hooks

Optional CI checks owned by individual stories. `tools/ci/run.py hooks` (TC-26) runs `<name>.py` for each name in its
`HOOKS` list once the file exists. Every hook is a standalone, standard-library-only script: exit 0 = pass.

## import-boundaries.py (TC-25)
Enforces the import rules of CLAUDE.md (rules 1 and 3), ADR-0001 and ADR-0004 section 8 over the Python and
TypeScript/JavaScript sources in `apps/`, `packages/` and `tests/`. Run it locally from the repo root:

```bash
uv run --no-project python tools/ci/hooks/import-boundaries.py
```

Each violation prints as `path:line: RULE message`; the rule list is in the script's docstring. Self-tests (one
violating and one clean fixture per rule) live in `tools/ci/tests/test_import_boundaries.py`:

```bash
uv run --no-project python -m unittest discover -s tools/ci/tests -t .
```

**Why a script and not import-linter / dependency-cruiser:** one check for both languages, no new dependencies, and
nothing needs to be installed or importable (the runner side's torch and rlgym-learn exist only in the user's
interpreter). The checks are static, so a backend unit test still asserts at runtime that torch and rlgym-learn are
not in `sys.modules` (ADR-0004 section 8).

To add a rule: add it to `_python_rules` or `check_typescript`, document it in the docstring, and add a violating and
a clean case to the self-tests.
