# tools/ci — repository checks (local and CI)

**Owner:** shared (`track-shared`). The GitHub Actions workflow [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
only calls [`run.py`](run.py), so what CI checks is exactly what you can run locally.

## Run the checks locally

From the repository root, with the toolchain from the root README (uv, Node 24, pnpm via Corepack):

```bash
uv run --no-project python tools/ci/run.py all
```

or one or more steps:

```bash
uv run --no-project python tools/ci/run.py lint typecheck test
```

| Step | What it runs |
|---|---|
| `install` | `uv sync --all-packages --locked`, `pnpm install --frozen-lockfile` |
| `lint` | per uv member with `[tool.ruff]`: `ruff check` + `ruff format --check`; `pnpm -r --if-present run lint` |
| `typecheck` | per uv member with `[tool.mypy]`: `mypy`; `pnpm -r --if-present run typecheck` |
| `test` | `tools/ci` self-tests; per uv member with a `tests/` folder or `[tool.pytest.ini_options]`: `pytest --basetemp=.ci-tmp/pytest/<member>` (includes QA's `tests/api`); `pnpm -r --if-present run test` |
| `build` | per uv member with `[build-system]`: `uv build` into `dist/python/`; `pnpm -r --if-present run build` |
| `hooks` | `tools/ci/hooks/contract-drift.py` (TC-18), `tools/ci/hooks/import-boundaries.py` (TC-25), `tests/fixtures/workspaces/generate.py --check` (TC-42), each only once it exists |

A step keeps going after a failure and lists every failure at the end; the exit code is non-zero if anything failed.
A check that is skipped (no tests, hook not written yet) prints a line saying so: nothing is skipped silently.

## Plugging in a new app or package
- **Python:** add it to `[tool.uv.workspace] members` in the root `pyproject.toml`, and give it `[tool.ruff]`,
  `[tool.mypy]`, a `tests/` folder and a `[build-system]` as appropriate (see `apps/backend/pyproject.toml`).
- **TypeScript:** add it to `pnpm-workspace.yaml` and define the `lint`, `typecheck`, `test` and `build`
  package.json scripts it needs. They must be non-interactive (no watch mode, headless browsers).
- **Hooks:** add `(name, script path, arguments)` to `HOOKS` in `run.py` (scripts normally live in
  `tools/ci/hooks/`). It runs with
  `uv run --locked --all-packages python`, from the repository root, and fails the build by exiting non-zero.

## Repository on an exFAT/FAT drive (Windows)
`pnpm install` cannot create symlinks there (see the root README). Set these for the shell, then run `install`
as usual; do not commit them:

```bash
export pnpm_config_node_linker=hoisted pnpm_config_hoist=false pnpm_config_package_import_method=copy
```

PowerShell: `$env:pnpm_config_node_linker='hoisted'; $env:pnpm_config_hoist='false'; $env:pnpm_config_package_import_method='copy'`.

## CI details
- Triggers: pull requests to `dev` and `main`, pushes to `dev`. Matrix: `ubuntu-latest` and `windows-latest`,
  `fail-fast: false` so both results are always visible. Job timeout: 15 minutes.
- Toolchain: uv via `astral-sh/setup-uv` (Python from `.python-version`, cache keyed on `uv.lock`), pnpm via
  `pnpm/action-setup` (version from `packageManager`), Node via `actions/setup-node` (version from `.nvmrc`, pnpm
  store cache).
- On failure, `*.log` files under `.ci-tmp/pytest/` (the API suite's `backend-*.log`) are uploaded as the
  `test-logs-<os>` artefact, kept 14 days.
- Required checks: `checks (ubuntu-latest)` and `checks (windows-latest)`.

## Manual step for the supervisor: branch protection on `dev`
GitHub → Settings → Branches (or Rules → Rulesets) → protect `dev`:
1. Require a pull request before merging.
2. Require status checks to pass: `checks (ubuntu-latest)` and `checks (windows-latest)` (they appear in the list
   after the workflow has run once).
3. Require branches to be up to date before merging (optional; avoids merging stale green runs).
4. Block force pushes and deletions.

Do the same for `main` once release PRs start.
