# apps/backend — FastAPI service

**Owner track:** A (`track-a`, DEV-A). **Language:** Python (uv workspace member `studio-backend`).

The local HTTP/WS service. It owns all training orchestration and all file-system access (ADR-0002), and spawns
training runs as local child processes (ADR-0003). Its OpenAPI schema is the source of truth of the API contract.

## Boundaries (ADR-0001)
- Packages never import from `apps/*`. Apps never import from each other: they talk only through the HTTP/WS
  contract (`packages/contract`).
- This folder must stay extractable into its own repository without code changes (own manifest, tests and README).
- **Never imports torch, rlgym or rlgym-learn** (owner decision). Training-side code is reached only through the host
  side of `packages/rlgym-adapter`.

## Run

From the repository root (after `uv sync --all-packages`):

```bash
uv run --package studio-backend python -m studio_backend --port 0
```

`studio-backend` (console script) is equivalent to `python -m studio_backend`.

| Setting | CLI | Environment variable | Default |
|---|---|---|---|
| Interface | `--host` | `STUDIO_BACKEND_HOST` | `127.0.0.1` |
| Port (`0` = any free port) | `--port` | `STUDIO_BACKEND_PORT` | `0` |
| Log level (`debug`, `info`, `warning`, `error`, `critical`) | `--log-level` | `STUDIO_BACKEND_LOG_LEVEL` | `info` |

Precedence: CLI > environment variable > default. Nothing is read from the working directory.

### Output contract
- **stdout** carries only machine-readable events, one compact JSON object per line. Once the server accepts
  connections it prints the handshake line, always the first stdout line:
  `{"event":"listening","port":12345}`. (TC-19 adds the per-launch token to it.)
- **stderr** carries logs, one JSON object per line: `{"ts", "level", "logger", "message"[, "exc_info"]}`.
- Exit codes: `0` normal stop, `1` cannot start (e.g. port in use), `2` invalid settings.

### API (0.1.0)
- `GET /api/health` → `200 {"status": "ok"}`
- `GET /api/version` → `200 {"app_version": "<package version>", "api_version": "<contract version>"}`
- Every error response has one shape (refined to problem+json in 0.9.0):
  `{"error": {"code": "not_found", "message": "Not Found", "details": null}}`. `code` is stable and meant for
  clients; `message` is for developers and logs.
- The OpenAPI schema is exported into `packages/contract/openapi.json` with
  `uv run --package studio-backend export-openapi` (`--check` to verify). Commit it with every route change; see
  `packages/contract/README.md`.

## Develop

From `apps/backend/`:

```bash
uv run --package studio-backend pytest
uv run --package studio-backend ruff check .
uv run --package studio-backend ruff format --check .
uv run --package studio-backend mypy
```

Layout: `src/studio_backend/` (`app.py` factory, `api/` routes, `settings.py`, `logging_config.py`, `errors.py`,
`server.py` socket binding + handshake), tests in `tests/`. `tests/test_dependencies.py` fails if torch, rlgym or
rlgym-learn ever enters the dependency tree or gets imported.
