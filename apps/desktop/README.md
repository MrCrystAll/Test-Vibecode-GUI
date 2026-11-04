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

## Lifecycle (TC-24)
- **Stop** (quit, window closed, Retry/Restart) is graceful first, then forced (`shutdown.ts`):
  1. close the backend's stdin. It runs with `STUDIO_BACKEND_SHUTDOWN_ON_STDIN_EOF=1`, so the end of file is its
     documented shutdown signal (apps/backend/README.md). Windows has no SIGTERM for a console child; a pipe closes
     the same way everywhere;
  2. wait up to 5 s for the serving python and the spawned process to exit;
  3. otherwise **kill the whole process tree**, then the handshake `pid` (`process-tree.ts`). On Windows `uv run` is
     uv → venv launcher → python, and killing only uv leaves python serving, so `taskkill /T /F` is used. On Linux the
     backend is spawned `detached` (its own process group) and the group is killed;
  4. check the PIDs are gone. `main.log` says `backend stop: graceful | killed | survived`.
- **Shell killed** (crash, Task Manager): the stdin pipe closes with the process, so the backend stops by itself.
  As a fallback, `<userData>/backend.pid` records the spawned and serving PIDs while the backend runs. At the next
  start, a leftover that is still alive *and* still has a `studio-backend`/`studio_backend` command line is killed
  (`pid-file.ts`; the command line check guards against reused PIDs).
- **Backend dies after start-up**: the state goes `ready → stopped`. The app stays on screen with a "backend stopped"
  banner (`backend-stopped`, button `backend-stopped-restart`). Restart spawns a new backend, so a new port and token;
  the UI goes through the splash and rebuilds its client.
- **Single instance per profile**: the lock is taken after `--user-data-dir` is applied, so e2e tests with their own
  profiles never collide. A second launch with the same profile exits (code 0) and the first one restores and focuses
  its window (`second launch: focusing the existing window` in `main.log`).

## Renderer security (TC-23 AC2)
`contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`. The preload (`preload.ts`) exposes only
`window.studio`, and nothing else:

| Function | What it does |
|---|---|
| `getBackendConnection()` | `{ baseUrl, wsUrl, token }` once the backend is ready; rejects before |
| `getStartupState()` / `onStartupState(listener)` | the backend's startup phase (never the token); the listener form returns an unsubscribe function |
| `retryBackend()` | starts a new backend after a failure or a crash |
| `quit()` | quits the app (stops the backend first) |
| `selectDirectory()` | opens the native folder dialog (with "new folder"), resolves to the chosen path or `null` on cancel (TC-46) |

The window refuses pop-ups and navigation to any other origin. Calls that open something on the desktop
(`selectDirectory`) are honoured only from the studio window's top frame at the UI origin; any other sender gets a
rejected promise (`select-directory.ts`). The renderer gets back a path string only, never file-system access.

## Configuration (dev and test)
| Flag / env var | Effect |
|---|---|
| `--user-data-dir=<path>` or `STUDIO_USER_DATA_DIR` | profile folder (one per e2e test). Logs go to `<userData>/logs/` |
| `STUDIO_UI_URL` | load the UI from this URL (e.g. `ng serve`) instead of the built files |
| `STUDIO_BACKEND_CMD` | backend command as a JSON array, e.g. a fake backend for tests (it gets `STUDIO_BACKEND_SHUTDOWN_ON_STDIN_EOF=1` too) |
| `STUDIO_BACKEND_STARTUP_TIMEOUT_MS` | startup timeout (default 30000) |
| `STUDIO_E2E=1` | **test mode** (ignored by a packaged app): enables the e2e hooks below |
| `STUDIO_E2E_SELECT_DIRECTORY` | test mode only: `selectDirectory()` answers this path without a dialog; `__cancel__` answers `null` |
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
**Electron binary (TC-48):** since Electron 45 the `electron` package has no install script, so pnpm's build
settings do not fetch the binary. This package's `postinstall` runs Electron's `install-electron` bin instead: a
fresh `pnpm install` leaves a working binary in `node_modules/electron/dist/`, downloaded once per machine and then
taken from Electron's cache. `start`, `dev` and CI's e2e step first run `scripts/check-electron.cjs`, which fails
with the fix when the binary is missing or from another version:

```bash
pnpm --filter @studio/desktop run check-electron     # "Electron binary OK: …" or what is wrong + the fix
pnpm --filter @studio/desktop run install-electron   # (re)download it; does nothing when it is already there
```

Vitest never launches Electron.
