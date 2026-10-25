# ADR-0005: Backend packaged with a bundled Python runtime

- Status: Proposed (2026-10-25)
- Ticket: TC-14

## Context
Owner decision (roadmap, decision 3): **the FastAPI backend ships with its own bundled Python, separate from the user's
training interpreter.** The API process never imports torch, and rlgym-learn is reached only through the adapter
package (CLAUDE.md rule 3). Introspection and training run in the user's interpreter (integration notes §7), so the
studio and the training environment cannot disagree on versions.

The bundled backend therefore contains only light, pure-wheel dependencies (FastAPI, uvicorn, pydantic, the adapter's
*host side*). It must run on Windows and Linux (no macOS, owner decision 2), start fast, stay small, not trigger
antivirus false positives on Windows, and be easy for Electron to find and spawn in dev and in packaged builds.
Installers, signing and auto-update (electron-builder + electron-updater) arrive in 1.0.0.

## Options considered

| | A. PyInstaller one-dir | B. python-build-standalone + installed deps | C. Nuitka standalone | D. python.org embeddable zip |
|---|---|---|---|---|
| What ships | Frozen bootloader `.exe` + `_internal/` with stdlib and deps | A stock, relocatable CPython (`install_only_stripped`) with our deps installed into its `site-packages` | Python compiled to C, native executable + DLLs | Minimal CPython for Windows, deps added by hand |
| Windows + Linux | Yes (build per OS) | Yes (build per OS; Linux builds target old glibc) | Yes (needs a C compiler per OS; MSVC on Windows) | **Windows only** → rejected |
| Startup | Fast in one-dir (one-file unpacks to temp and is slow) | Normal CPython start; fast with `.pyc` precompiled at build time | Fastest in theory | Normal |
| Size (estimate, measured in 0.8.0) | Similar to B | Similar to A; can drop `tkinter`, `idlelib`, `test`, `ensurepip` | Similar or larger | Smallest |
| Antivirus (Windows) | **Frequent false positives**: the PyInstaller bootloader is widely reused by malware | Low: stock `python.exe`/DLLs, no self-extraction, no packing | Medium: one-file mode flagged often; standalone less | Low |
| Build complexity | Hidden-import / hook tuning for uvicorn, pydantic, our plugins; breaks on dependency upgrades | Low: `uv` installs the locked dependencies into the runtime; no freezing | High: long builds, C toolchain in CI, plugin tuning | Manual `._pth` editing, no pip |
| Debuggability | Frozen; tracebacks OK but no REPL, `sys.frozen` special cases | **Same interpreter and code layout as in dev**; `python -m` works | Compiled; harder to debug | Normal |
| Licence | GPL-2.0 with bootloader exception (distribution allowed) | CPython PSF licence + build libs' licences | Apache-2.0 | PSF |

## Decision
**Option B: ship a relocatable CPython from `python-build-standalone` with the backend and its locked dependencies
installed into it.** It has the lowest antivirus risk, the simplest build, and no frozen-mode differences between dev
and packaged builds. `uv` itself installs Python from these same builds, so developers and users run the same CPython.

### Bundle layout (packaged app)
```
<app resources>/backend/
  python/                 # python-build-standalone install_only_stripped, pinned version + SHA-256
    python.exe | bin/python3
    Lib/site-packages/ | lib/python3.X/site-packages/   # backend + adapter host side + locked deps
  BUNDLE.json             # python version, backend version, lockfile hash (for diagnostics)
```
Build steps (CI, per OS, implemented in 0.8.0):
1. Download the pinned runtime archive and verify its SHA-256 (cached in CI; no network at app runtime).
2. `uv export --frozen --no-dev --package <backend>` → install those exact wheels into the runtime's `site-packages`
   (`uv pip install --python <runtime> --no-deps --require-hashes -r ...`), then install the backend and adapter host
   side the same way.
3. Remove unused stdlib parts, precompile with `python -m compileall` (the install dir is read-only at runtime).
4. **Guard:** the build fails if `torch`, `rlgym`, `rlgym_learn` or `rlgym_learn_algos` is found in the bundle.
   Together with the import-boundary lint (TC-25) this enforces "no torch in the API process".
5. electron-builder copies `backend/` as `extraResources`.

### How Electron spawns the backend
Electron's main process has one `BackendLauncher` interface with two implementations, picked by `app.isPackaged`.
Both produce the **same command-line contract** and the same stdout handshake (port + token, TC-23):

| Mode | Command | Working directory |
|---|---|---|
| Dev (`!app.isPackaged`) | `uv run --frozen --project apps/backend python -m <backend_module> <args>` | repo root |
| Packaged | `<resourcesPath>/backend/python/{python.exe \| bin/python3} -I -B -m <backend_module> <args>` | user data dir |

- `-I` (isolated mode) ignores `PYTHONPATH`, `PYTHONHOME` and the user site directory, so a user's conda or venv
  settings cannot leak into the backend. The launcher also removes `PYTHON*` variables and `VIRTUAL_ENV` from the
  child's environment. In dev the same scrub applies, but `uv run` controls the environment.
- `-B` because the install directory is read-only (Program Files, AppImage); `.pyc` files are precompiled.
- A dev-only override `STUDIO_BACKEND_CMD` lets a developer start the backend under a debugger. It is ignored in
  packaged builds.
- The backend never spawns the training with its own interpreter: training and introspection always use the
  per-project user interpreter (0.3.0), launched through the adapter.

### When it gets implemented
- **0.1.0:** dev mode only. Electron (TC-23) spawns `uv run`; the `BackendLauncher` interface exists with the dev
  implementation.
- **0.8.0 (A5):** the bundled implementation, the CI bundle build on Windows and Linux, and an installable dev build
  for testers. Startup time and size are measured and recorded in this ADR.
- **1.0.0:** electron-builder installers, Authenticode signing of the bundled `python.exe`, `.pyd` and `.dll` files
  together with the app (S2), and auto-update. The bundle is part of the app, so it updates with the app; there is no
  separate Python updater.

### What 0.1.0 must not preclude
- The backend starts as `python -m <backend_module>` with all settings from CLI arguments or environment variables,
  never from the current working directory or repo-relative paths. Package data is read with `importlib.resources`.
- The backend never writes inside its install directory; logs and state go to the user data directory or workspace.
- Dependencies are available as wheels for Windows x64 and Linux x64 (no compiler needed at install time), and
  `uv.lock` is committed.
- No dependency on torch, rlgym or rlgym-learn in the backend or the adapter's host side.
- Electron code talks to a `BackendLauncher`, never to a hard-coded `uv` command.

## Consequences
- One CPython per OS to pin and update (security fixes in Python become a bundle bump, done as a story).
- No freezing step to maintain; dependency upgrades do not need hook tuning.
- The bundle exposes plain `.py`/`.pyc` files. That is fine for an Apache-2.0 open project, and it makes user bug
  reports easier to diagnose.
- Size is roughly the same as PyInstaller; if size becomes a problem, trim the stdlib further before switching tools.
- If Option B ever fails on a platform, PyInstaller one-dir is the fallback; the `BackendLauncher` interface keeps that
  change inside the Electron shell and the bundle build.
