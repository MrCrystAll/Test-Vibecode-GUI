# rlgym-learn studio (working title)

Desktop app to configure, run, debug, monitor and track RL agents trained with
[rlgym-learn](https://github.com/JPK314/rlgym-learn). Electron + Angular + FastAPI.

- Contributor guide and architecture rules: [CLAUDE.md](CLAUDE.md)
- Team workflow: [docs/process/workflow.md](docs/process/workflow.md)
- Product vision and roadmap: [docs/product/](docs/product/)

## Repository layout (ADR-0001)

| Folder | What | Track | Workspace |
|---|---|---|---|
| `apps/backend/` | FastAPI service | A | uv |
| `apps/ui/` | Angular UI | B | pnpm |
| `apps/desktop/` | Electron shell | B | pnpm |
| `packages/contract/` | `openapi.json` + generated TS client | shared | pnpm |
| `packages/config-schema/` | studio file schemas and migrations | A | uv |
| `packages/rlgym-adapter/` | the only bridge to rlgym-learn | A | uv |

Packages never import from apps; apps talk to each other only through the HTTP/WS contract.

## Toolchain (pinned)

| Tool | Version | Pinned in | Why |
|---|---|---|---|
| Python | 3.12 | `.python-version` | Backend runtime (bundled with the app later, ADR-0005). 3.12 is supported by rlgym-learn, torch and the whole tooling ecosystem; the runner side of the adapter also supports the user's own interpreter (>= 3.10). |
| uv | >= 0.13 | `pyproject.toml` (`[tool.uv] required-version`) | Python workspace + lockfile (`uv.lock`); installs Python 3.12 itself if missing. |
| Node.js | 24 (LTS) | `.nvmrc`, `package.json` `engines` | UI and Electron tooling. |
| pnpm | 12.15.0 | `package.json` `packageManager` (Corepack) | TS workspace + lockfile (`pnpm-lock.yaml`), strict dependency isolation. |

Two workspaces live side by side: a **uv workspace** (root `pyproject.toml`) for the Python members and a
**pnpm workspace** (`pnpm-workspace.yaml`) for the TypeScript members. Both lockfiles are committed.

## Getting started

Prerequisites: Git, [uv](https://docs.astral.sh/uv/getting-started/installation/) and Node.js 24 (Corepack ships with it).

```bash
git clone https://github.com/MrCrystAll/Test-Vibecode-GUI.git
cd Test-Vibecode-GUI
uv sync --all-packages        # Python: installs Python 3.12 if needed, creates .venv
corepack enable               # once per machine; may need an admin shell on Windows
pnpm install --frozen-lockfile  # TypeScript workspace
```

Without `corepack enable`, use `corepack pnpm install --frozen-lockfile` instead.
Per-app commands (run, test, lint, build) are documented in each folder's README as they are added.

### Troubleshooting: repository on an exFAT/FAT drive (Windows)
exFAT supports neither symlinks nor junctions, so `pnpm install` fails with `Failed to create symlink ... Incorrect
function. (os error 1)`. Prefer cloning onto an NTFS drive. As a local workaround (do not commit it), install with:

```bash
pnpm install --frozen-lockfile --config.node-linker=hoisted --config.hoist=false --config.package-import-method=copy
```

## License
Licensed under the [Apache License, Version 2.0](LICENSE). See [NOTICE](NOTICE) for attribution and
[docs/process/licensing.md](docs/process/licensing.md) for the source-header and third-party code policy.
