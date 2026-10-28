# apps/desktop — Electron shell

**Owner track:** B (`track-b`, DEV-B). **Language:** TypeScript (pnpm workspace member `@studio/desktop`).

Main process only: window, lifecycle, spawning and supervising the backend (port + token handshake on its stdout).
No business logic here: the backend owns it, and the Angular UI shows every screen, including the splash and the
startup error (so all user-visible strings stay in the UI's i18n catalogue).

## Boundaries (ADR-0001)
- Packages never import from `apps/*`. Apps never import from each other: they talk only through the HTTP/WS
  contract (`packages/contract`).
- This folder must stay extractable into its own repository without code changes (own manifest, tests and README).

## Run it (dev mode, Windows and Linux)
From the repository root, with the toolchain from the root README (uv, Node 24, pnpm):

```bash
pnpm --filter @studio/desktop dev     # builds the UI and the shell, then starts Electron
```

`dev` = `pnpm --filter @studio/ui build` + `tsc` + `electron .`. After a first build, `pnpm --filter @studio/desktop
start` (just `electron .`) is enough. To work on the UI with live reload, run `pnpm --filter @studio/ui start` and
start the shell with `STUDIO_UI_URL=http://localhost:4200`. The backend then allows that origin automatically.

Scripted launch (e.g. Playwright's `_electron.launch`, TC-29): the entry is `apps/desktop` (its `main` is
`dist/main.js`); run `pnpm --filter @studio/ui build` and `pnpm --filter @studio/desktop build` first.

## What happens at start (TC-23)
1. The UI is served from the privileged custom scheme `studio://app/` (files of `apps/ui/dist/ui/browser`, with
   client-side routes falling back to `index.html`). The window opens at once and shows the splash.
2. The backend is spawned in dev mode (ADR-0005): `uv run --package studio-backend studio-backend` from the repo root,
   with `STUDIO_BACKEND_ALLOWED_ORIGINS` set to the renderer's origin (`studio://app`), as TC-19 requires.
3. Its first stdout line is the handshake `{"event":"listening","port":…,"token":"…","pid":…}` (`handshake.ts`). The
   token stays in the main process's memory; logs only ever show `pid` and `port`.
4. `GET /api/health` is polled until it answers 200 (`health.ts`), within the startup timeout (30 s).
5. The UI is told `ready` and asks for the connection; it never sees anything else from Node.

Any failure (cannot spawn, exits, bad handshake, timeout) moves the state machine (`startup.ts`) to `failed`, kills
the attempt's process tree, and the UI shows the error with **Retry** and **Quit**.

**Stopping the backend kills the whole process tree**, then the handshake `pid` (`process-tree.ts`). On Windows `uv run`
is uv → venv launcher → python, and killing only the spawned uv leaves python serving: `taskkill /T /F` is used. On
Linux the backend is spawned `detached` (its own process group) and the group is killed. Graceful shutdown, crash
detection and the single-instance lock are TC-24.

## Renderer security (TC-23 AC2)
`contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`. The preload (`preload.ts`) exposes only
`window.studio`: `getBackendConnection()`, `getStartupState()`, `onStartupState(listener)`, `retryBackend()`, `quit()`.
The window refuses pop-ups and navigation to any other origin.

## Configuration (dev and test)
| Flag / env var | Effect |
|---|---|
| `--user-data-dir=<path>` or `STUDIO_USER_DATA_DIR` | profile folder (one per e2e test). Logs go to `<userData>/logs/` |
| `STUDIO_UI_URL` | load the UI from this URL (e.g. `ng serve`) instead of the built files |
| `STUDIO_BACKEND_CMD` | backend command as a JSON array, e.g. a fake backend for tests |
| `STUDIO_BACKEND_STARTUP_TIMEOUT_MS` | startup timeout (default 30000) |
| `STUDIO_E2E_NO_SANDBOX=1` | Chromium `--no-sandbox`, **only** for Linux CI containers (with `xvfb-run`); the renderer stays sandboxed |

Logs: `<userData>/logs/main.log` (the shell: `backend starting`, `backend started pid=… port=…`, failures, exit) and
`<userData>/logs/backend.log` (the backend's stderr, which is its JSON log, and any later stdout).

## Develop
```bash
pnpm --filter @studio/desktop lint
pnpm --filter @studio/desktop typecheck
pnpm --filter @studio/desktop test    # Vitest, pure modules only: no Electron is launched
pnpm --filter @studio/desktop build   # tsc -> dist/
```
`electron` downloads its binary the first time it is required; CI never launches it.
