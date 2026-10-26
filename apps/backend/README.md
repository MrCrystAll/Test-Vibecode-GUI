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
| Interface (only `127.0.0.1` unless the dev flag below is set) | `--host` | `STUDIO_BACKEND_HOST` | `127.0.0.1` |
| Port (`0` = any free port) | `--port` | `STUDIO_BACKEND_PORT` | `0` |
| Log level (`debug`, `info`, `warning`, `error`, `critical`) | `--log-level` | `STUDIO_BACKEND_LOG_LEVEL` | `info` |
| API token (≥ 32 chars of `A-Z a-z 0-9 - _ . ~`); **env only**, command lines are visible to other users | — | `STUDIO_BACKEND_TOKEN` | random, 256 bits, per launch |
| Browser origins allowed to call the API (e.g. `http://localhost:4200` for `ng serve`) | `--allowed-origin` (repeatable) | `STUDIO_BACKEND_ALLOWED_ORIGINS` (comma-separated) | none |
| Development only: allow a non-loopback `--host` (logs a warning) | `--unsafe-bind-any` | `STUDIO_BACKEND_UNSAFE_BIND_ANY=1` | off |

Precedence: CLI > environment variable > default. Nothing is read from the working directory.

### Output contract
- **stdout** carries only machine-readable events, one compact JSON object per line. Once the server accepts
  connections it prints the **handshake line**, always the first stdout line (a contract with Electron, TC-23):

  ```json
  {"event":"listening","port":12345,"token":"<per-launch token>","pid":4321}
  ```

  | Key | Meaning |
  |---|---|
  | `port` | the TCP port on `127.0.0.1` (the real one when started with `--port 0`) |
  | `token` | the bearer token every request except `/api/health` needs; keep it in memory, never log or persist it |
  | `pid` | the PID of the Python process serving the API. On Windows `uv run` and venv launchers sit in front of it, so the PID the parent spawned is not this one: stop the whole tree, and use `pid` to check it is gone |

  New keys may be added; consumers ignore keys they don't know.
- **stderr** carries logs, one JSON object per line: `{"ts", "level", "logger", "message"[, "exc_info"]}`.
  The token is replaced by `***` everywhere in the logs (e.g. a WebSocket `?token=` in an access-log line).
- Exit codes: `0` normal stop, `1` cannot start (e.g. port in use), `2` invalid settings.

### Local security (TC-19)
Only the client that launched the backend can drive it:
- It binds to `127.0.0.1` only; any other `--host` exits with code 2 unless `--unsafe-bind-any` is set.
- Every request is checked before routing, in this order:
  1. `Host` must be `127.0.0.1` or `localhost` (any port), which defeats DNS rebinding → `400 invalid_host`.
  2. An `Origin` header, if present, must be an allowed origin → `403 origin_not_allowed`. Browsers always send
     one; Electron's main process, the CLI and tests send none.
  3. Every route except `GET /api/health` (including unknown routes and `/openapi.json`) needs
     `Authorization: Bearer <token>` → `401 unauthorized` with `WWW-Authenticate: Bearer`.
- WebSockets: the same checks on the handshake. Browsers cannot set headers on a WebSocket, so the token may also be
  passed as `?token=<token>` (WebSocket only, never accepted over HTTP). A refused handshake is closed with code
  `1008` before `accept` (seen as HTTP 403 by the client).
- CORS: allowed origins get CORS headers for `Authorization` and `Content-Type`; preflights carry no token by design
  and are answered without one.

### API (0.1.0)
- `GET /api/health` → `200 {"status": "ok"}` (no token needed: liveness probe)
- `GET /api/version` (token) → `200 {"app_version": "<package version>", "api_version": "<contract version>"}`
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
