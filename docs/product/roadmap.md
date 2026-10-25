# Roadmap to 1.0.0

Owner: `[PO]`. Status: **draft, awaiting owner approval** (2026-10-25). No Jira epics exist yet.
Inputs: [vision.md](vision.md), [rlgym-learn-integration-notes.md](rlgym-learn-integration-notes.md), ADR-0001..0003.

## How to read this
- One epic = one minor version = one Jira epic + fix version (see [workflow](../process/workflow.md)).
- Each epic lists **two developer tracks (A / B) that do not touch the same folders**, plus a QA track, so DEV-A and
  DEV-B can work in parallel without merge conflicts. Track letters are a planning aid; any developer can pick any
  story, but stories in the same track are usually sequential.
- Default ownership by area (keeps tracks non-overlapping):
  - **Track A — backend side:** `apps/backend/`, `packages/rlgym-adapter/`, `packages/config-schema/` (Python).
  - **Track B — client side:** `apps/ui/`, `apps/desktop/`, generated client in `packages/contract/` (TypeScript).
  - The contract (OpenAPI) is the seam: every cross-track feature starts with a small contract story (endpoint +
    schema, stubbed backend) so track B can build against the generated client while track A implements it.
- A **fake runner** (introduced in 0.4.0) emits the real event stream and file layout without torch/rlgym, so UI,
  e2e tests and CI never need a GPU or rlgym installed.
- Candidate stories are one line each; they will be refined into Jira stories with acceptance criteria in Phase 1.

## Epic overview

| Version | Epic | Goal (one line) |
|---|---|---|
| 0.1.0 | Foundations | Monorepo skeleton, CI, OpenAPI → TS client pipeline, Electron spawns and supervises the backend, QA harness. |
| 0.2.0 | Workspace & persistence | Projects stored as versioned files in a user workspace, with migrations and a rebuildable index. |
| 0.3.0 | Python environment & entrypoint | Pick and validate the user's training interpreter; define the entrypoint contract; introspect config schema. |
| 0.4.0 | Run lifecycle | Launch, pause, checkpoint, stop and kill training runs as local child processes, with live logs. |
| 0.5.0 | Live monitoring | Per-iteration metrics written to disk and streamed live; charts and run health. |
| 0.6.0 | Config editor | Schema-driven forms over the upstream config, with raw JSON, validation, presets and multi-controller support. |
| 0.7.0 | Checkpoints & run history | Browse, resume, fork, compare and clean up runs and checkpoints. |
| 0.8.0 | Debugging & diagnostics | Actionable errors for crashes, env-process failures, interpreter/CUDA problems; log search; render toggle. |
| 0.9.0 | Public API & extension points | Versioned, documented HTTP/WS API, config schema and extension points ready to freeze. |
| 1.0.0 | Stable release | Installers, docs, upgrade path, betas; freeze the public API under semver. |

```
0.1 ──► 0.2 ──► 0.3 ──► 0.4 ──► 0.5 ──► 0.6 ──► 0.7 ──► 0.8 ──► 0.9 ──► 1.0
             (persistence) (interpreter) (runs)  (metrics) (editor) (history) (debug) (API freeze prep)
```
Hard dependencies are listed per epic. 0.5 and 0.6 are only loosely coupled (both need 0.4); if one track runs
dry, its next stories may be pulled forward (see open question 8).

---

## 0.1.0 — Foundations
**Goal:** a contributor can clone, build, test and launch an empty desktop app whose UI talks to the backend through a
generated client, and CI proves it on every PR.

**Scope**
- Track A
  - A1 Monorepo skeleton: `apps/*`, `packages/*` folders, root README per package, tooling versions pinned (Node, Python, uv/pnpm).
  - A2 FastAPI app skeleton: `/api/health` + `/api/version`, settings, structured logging, pytest + ruff + mypy/pyright.
  - A3 OpenAPI export script + `packages/contract` holding the committed `openapi.json`; CI fails if it drifts from the code.
  - A4 Backend local security: bind `127.0.0.1` on an ephemeral port, require a per-launch bearer token on HTTP and WS.
  - A5 WebSocket skeleton: one `/ws` endpoint with an envelope (`type`, `version`, `payload`) and a ping event.
- Track B
  - B1 Angular skeleton: standalone components, strict TS, feature-sliced folders, lint + unit tests.
  - B2 TS client generation from `openapi.json` (generator choice in an ADR), consumed by the UI; health screen.
  - B3 Electron shell: spawns the backend, reads port + token from its stdout handshake, waits for health, shows the UI.
  - B4 Lifecycle: graceful backend shutdown on app quit, crash detection with restart prompt, single-instance lock.
  - B5 Import-boundary lint: packages never import apps; UI only talks to the backend via the generated client.
- Shared / CI
  - C1 CI pipeline (Windows + Linux): lint, unit tests, contract drift check, build of all apps.
  - C2 Conventional-commit check and pre-release tagging helper script (`v0.N.0-alpha.K`).
- QA
  - Q1 E2E harness: Playwright driving the Electron app; smoke test "app starts, health is green".
  - Q2 Backend API test harness (pytest + httpx) and test-data fixtures folder convention.
- PO/Supervisor: ADR-0004 two-sided rlgym adapter; ADR-0005 backend packaging; ADR on client generator.

**Exit criteria:** CI green on Windows and Linux; `app starts → health green` e2e passes; changing a backend route
without regenerating the client fails CI; backend refuses requests without the token; quitting the app leaves no
backend process.

**Dependencies:** owner answers to open questions 1-3 (repo hosting/CI, platforms, backend packaging).

---

## 0.2.0 — Workspace & persistence
**Goal:** users create and open projects that live as human-readable, versioned files in a workspace folder they choose.

**Scope**
- Track A
  - A1 Workspace model: user-chosen root, app settings file, folder layout spec (`<workspace>/<project>/project.json`, `runs/<run-id>/…`).
  - A2 `packages/config-schema`: studio envelope models (`schemaVersion`, metadata, embedded upstream config verbatim) + published JSON Schema.
  - A3 Migration framework: ordered forward migrations per file type, run on load, backup before rewrite, unit-tested fixtures per version.
  - A4 Project CRUD API (create, list, get, rename, archive, delete-to-trash) with atomic writes and file locking.
  - A5 Rebuildable index (in memory or cache file, never the source of truth) + filesystem watcher for external edits.
- Track B
  - B1 First-run flow: pick or create workspace; remember it in app settings.
  - B2 Project list and project detail shell (navigation, empty states).
  - B3 Create / rename / archive / delete project dialogs with validation errors from the API.
  - B4 Reactive refresh when files change outside the app (WS event from A5).
- QA: e2e for project CRUD; migration test corpus (old-version files must load); manual test: edit a file by hand.

**Exit criteria:** projects survive app restart and manual edits; opening an older `schemaVersion` file migrates it
and keeps a backup; deleting the index loses nothing; the JSON Schema for project files is published in `packages/config-schema`.

**Dependencies:** 0.1.0.

---

## 0.3.0 — Python environment & entrypoint
**Goal:** a project knows which Python interpreter trains it, the studio verifies it works, and the studio can obtain
the exact config schema of the user's training code.

**Scope**
- Track A
  - A1 Adapter host side: interpreter discovery (PATH, venvs, conda), per-project interpreter setting.
  - A2 Adapter runner side (runs in the user's Python, no studio deps): `introspect` command reporting Python, rlgym, rlgym-learn, algos, torch, CUDA devices, wandb.
  - A3 Entrypoint contract v0: a user module exposing `build(ctx) -> (env_create_function, agent_controller)`; documented and validated (importable, spawn-safe).
  - A4 Config-schema introspection: the runner instantiates the user's components and emits the concrete JSON Schema + defaults of `LearningCoordinatorConfigModel`.
  - A5 Supported-version matrix (rlgym-learn 2.0.x, algos 0.4.x initially) with clear "unsupported version" errors.
- Track B
  - B1 Interpreter picker + environment status panel (versions, GPU list, problems with fix hints).
  - B2 Entrypoint picker and "check entrypoint" action with readable error display.
  - B3 Project template gallery: create a project from the upstream quick-start (Rocket League PPO) template.
- QA: tests with a fake interpreter fixture (no torch) and one real-environment manual test plan; e2e "create from template, check env".

**Exit criteria:** with a valid environment, "check" shows versions and devices and fetches a schema; with a broken one
(missing torch, wrong rlgym-learn version, non-importable entrypoint) the user sees a specific, actionable error; the
backend process never imports torch or rlgym.

**Dependencies:** 0.2.0 (projects store interpreter/entrypoint); ADR-0004.

---

## 0.4.0 — Run lifecycle
**Goal:** start, control and stop a real training run from the UI, safely, with live console output.

**Scope**
- Track A
  - A1 Run folder and `run.json` (status, config snapshot, interpreter, upstream versions, timestamps); cwd = run folder.
  - A2 Runner: `LearningCoordinator` subclass whose `process_kbhit` reads a control channel; commands pause, resume, checkpoint, stop-with-checkpoint, add/remove env process.
  - A3 Process supervision: start, process-tree kill (Windows job object / POSIX process group), orphan cleanup on backend start, `shmem_flinks` cleanup.
  - A4 Structured run events (started, heartbeat, paused, checkpoint-saved, stopped, completed, crashed) + log capture to `logs/stdout.log`.
  - A5 Fake runner implementing the same events and file layout, selectable per project (used by CI/e2e).
  - A6 Run API: start / control / list / get + WS streams for status and log lines.
- Track B
  - B1 Run launcher (raw JSON config editor with schema validation for now), start button, guarding against two runs in one folder.
  - B2 Run control bar: pause/resume, checkpoint now, stop, force kill (with confirmation), env-process +/-.
  - B3 Live console view with follow/scroll-lock, ANSI stripping, download log.
  - B4 Run list per project with live status badges.
- QA: e2e with the fake runner for every control command and crash path; manual test plan with a real quick-start run.

**Exit criteria:** a quick-start run can be started, paused, checkpointed and stopped from the UI and produces a
checkpoint on stop; killing the app does not leave orphaned env processes after next start; crash of the training
process is shown as `crashed` with the traceback.

**Dependencies:** 0.3.0 (interpreter, entrypoint, schema).

---

## 0.5.0 — Live monitoring
**Goal:** watch a run's learning progress live, offline, and keep the data for later.

**Scope**
- Track A
  - A1 Studio metrics logger (runner side): wraps the user's `DictMetricsLogger` (and/or wandb logger), appends `metrics.jsonl` per iteration per controller.
  - A2 `metrics.jsonl` format v1 (documented, versioned) + backend tailing and WS streaming with resume-from-offset.
  - A3 Metrics query API: series list, downsampled ranges, latest values, per controller.
  - A4 Health signals: steps/s, time since last iteration/heartbeat, env process count, stall detection.
- Track B
  - B1 Charting component (library chosen in an ADR) with time/timestep x-axis, smoothing, zoom.
  - B2 Run dashboard: default PPO panels (reward, entropy, KL, critic loss, clip fraction, SPS) + any custom nested metrics.
  - B3 Health strip: status, SPS, timesteps vs limit, ETA, last checkpoint.
  - B4 Multi-controller views (one tab/series per subcontroller).
- QA: fake runner emits deterministic metrics; e2e asserts charts update live and after app restart.

**Exit criteria:** metrics appear within one iteration of being produced, survive backend/app restarts, custom env
metrics are rendered without code changes, and wandb still works when enabled.

**Dependencies:** 0.4.0.

---

## 0.6.0 — Config editor
**Goal:** configure a run through validated forms instead of JSON, without ever losing access to the raw config.

**Scope**
- Track A
  - A1 Validation endpoint: validate a config against the introspected schema (pydantic errors mapped to JSON pointers).
  - A2 UI hints overlay for well-known models (PPO learner, experience buffer, GAE, process, wandb): labels, units, ranges, docs.
  - A3 Config presets/snapshots per project stored as files; diff between two configs.
  - A4 Run parameters file (optional): values the entrypoint may read (e.g. reward weights) — contract v1 of entrypoint.
- Track B
  - B1 Schema-driven form renderer (nested models, unions, optional/null, dicts) with generic fallback to JSON.
  - B2 Form ⇄ raw JSON two-way sync; inline validation messages.
  - B3 Multi-controller editing (`subcontrollers_config` keyed by name).
  - B4 Config diff view and "start run from preset".
- QA: schema corpus tests (PPO, multi-agent, wandb, custom user model); e2e for edit → validate → launch.

**Exit criteria:** every field of the quick-start and multi-agent example configs is editable via forms; invalid values
are rejected before launch with the field highlighted; raw JSON edits round-trip without loss.

**Dependencies:** 0.3.0 (schema), 0.4.0 (launch). Independent of 0.5.0.

---

## 0.7.0 — Checkpoints & run history
**Goal:** every past run is findable, comparable and resumable.

**Scope**
- Track A
  - A1 Checkpoint watcher: detect complete checkpoints (`ppo_agent.json` written last), handle pruning, read progress.
  - A2 Resume and fork: new run from a checkpoint (same run folder vs new run, editable config, lr changes); lineage in `run.json`.
  - A3 Keep/protect checkpoints by copying out of the pruned folder; export model weights.
  - A4 Run history API: filter/sort by project, status, tags, date; tags and notes on runs; disk usage; delete-to-trash.
  - A5 Import an existing (non-studio) rlgym-learn run folder; optional rlgym-ppo checkpoint conversion.
- Track B
  - B1 Run history table with filters, tags, notes.
  - B2 Checkpoint timeline per run with resume/fork/keep/export actions.
  - B3 Run comparison: overlay metrics of several runs; config diff between runs.
  - B4 Lineage view (resumed-from / forked-from).
- QA: e2e resume/fork with the fake runner; real-run manual test: stop, resume, verify cumulative timesteps continue.

**Exit criteria:** a run can be resumed or forked from any complete checkpoint in two clicks; comparisons work across
at least 5 runs; the studio never writes inside upstream checkpoint folders.

**Dependencies:** 0.4.0, 0.5.0 (comparison uses metrics).

---

## 0.8.0 — Debugging & diagnostics
**Goal:** when something goes wrong, the user knows what and what to do next.

**Scope**
- Track A
  - A1 Error classifier for common failures (import error, CUDA unavailable, OOM, serde/space mismatch, entrypoint not spawn-safe, config validation) with fix hints.
  - A2 Env-process failure tracking (close reasons, counts over time) surfaced as events.
  - A3 Diagnostics bundle export (logs, run.json, versions, config; no checkpoints) for bug reports.
  - A4 Resource sampling: CPU/RAM/GPU per run process tree.
  - A5 Backend packaging implementation per ADR-0005 (installable dev build for testers).
- Track B
  - B1 Problems panel per run with grouped, explained errors and links to logs.
  - B2 Log search/filter (level, text, time range) across stdout and studio events.
  - B3 Render toggle (`render`, `render_delay`) and "open rlviser" guidance.
  - B4 Resource charts.
- QA: fault-injection fixtures in the fake runner for every classified error; exploratory session on Windows.

**Exit criteria:** each classified failure shows a specific message and hint in e2e; a diagnostics bundle is
reproducible and contains no secrets (wandb keys) or checkpoints.

**Dependencies:** 0.4.0, 0.5.0.

---

## 0.9.0 — Public API & extension points
**Goal:** everything a third party needs to build on the studio is versioned, documented and tested as a contract.

**Scope**
- Track A
  - A1 API review and cleanup: consistent resources, error model (problem+json), pagination, `/api/v1` prefix.
  - A2 WS event catalogue with JSON Schemas and versioned envelopes; contract tests for every event.
  - A3 Freeze candidates: project/run file schemas, `metrics.jsonl` v1, entrypoint contract v1, control commands; deprecation policy.
  - A4 Local API access for third parties: discoverable endpoint + token file in the workspace, documented security model.
  - A5 Extension point: custom metric panels / run-event consumers via the public API only (no in-process plugins).
- Track B
  - B1 API reference site generated from OpenAPI + event schemas (in repo docs).
  - B2 Example third-party client (small read-only CLI or dashboard) built only on the published API, in `examples/`.
  - B3 UI migrated to `/api/v1` with no private endpoints left.
- QA: contract test suite run against the backend in CI; compatibility test: 0.8 data folders open in 0.9.

**Exit criteria:** the example client works using docs only; every endpoint and event has a schema and a test; no UI
feature depends on an undocumented endpoint; breaking-change checker (OpenAPI diff) wired into CI.

**Dependencies:** 0.4.0–0.8.0 functionally complete.

---

## 1.0.0 — Stable release
**Goal:** ship an installable, documented product whose public API is frozen under semver.

**Scope**
- Track A
  - A1 OpenAPI breaking-change gate becomes blocking; schema `schemaVersion` set to 1 for all public files with migrations from every 0.x format.
  - A2 Performance pass: long runs (days, 10^5 iterations of metrics), large workspaces (hundreds of runs).
  - A3 Security review of the local API, path handling and file deletion.
- Track B
  - B1 Installers for supported platforms (signed if possible), update notification (no silent auto-update).
  - B2 Onboarding: first-run tour, template-based quick start, in-app links to docs.
  - B3 Accessibility and keyboard navigation pass; UI polish backlog.
- Docs: user guide, entrypoint authoring guide, API/extension guide, upgrade notes from 0.x.
- QA: full regression on Windows and Linux; beta programme (`v1.0.0-beta.N`); sign-off checklist.

**Exit criteria:** installers work on clean machines; all 0.x workspaces migrate; public API, config schema and extension
points are documented and covered by contract tests; QA sign-off; release tagged `v1.0.0`.

**Dependencies:** 0.9.0.

---

## Explicitly out of scope for 1.0
- Remote, cloud or distributed training (permanent non-goal, ADR-0003).
- Database-backed storage (ADR-0002).
- Hyper-parameter sweeps, schedulers, queues of runs.
- Visual editors for reward functions, obs builders, state mutators or network architecture (code stays code;
  only parameters exposed via the run parameters file).
- Embedded 3D match viewer (we only toggle upstream `render` / rlviser).
- In-process plugins loaded into the backend or UI (extension is via the public API and the entrypoint contract).
- Installing or managing Python, torch or CUDA for the user.
- Algorithms other than what the user's entrypoint provides (we ship PPO templates only).
- Multi-user, sharing service, accounts, telemetry.
- macOS support (unless the owner decides otherwise, see question 2).
- Support for rlgym-learn 1.x.

---

## Open questions for the human owner
1. **Repository hosting and CI:** GitHub (which org/repo name) with GitHub Actions? CI from 0.1.0 needs this; there is no remote yet.
2. **Platforms for 1.0:** Windows + Linux (what rlgym-learn supports)? Is macOS wanted at all?
3. **Backend distribution:** ship the FastAPI backend bundled with its own Python (PyInstaller/embedded, recommended) separate from the user's training interpreter, or require users to install the backend into their own Python?
4. **Entrypoint contract:** OK that users write a small `build()` entrypoint module (we provide templates) rather than the studio trying to run arbitrary existing scripts?
5. **Supported upstream versions:** target only rlgym-learn 2.0.x / rlgym-learn-algos 0.4.x at first, and add newer versions as stories?
6. **Scope of domain:** generic RLGym core with Rocket League as the template/first-class example, or Rocket League-only?
7. **wandb:** keep it as an optional pass-through (configured, not reimplemented), with our local metrics as the primary view?
8. **Lookahead between epics:** may a developer start stories of the next epic (tagged under that version) when the current epic has no unblocked work for them, or must epics be strictly sequential?
9. **License** of the project (affects third-party ecosystem at 1.0): MIT/Apache-2.0, or proprietary?
10. **Upstream contributions:** may we propose PRs to rlgym-learn (e.g. a non-keyboard control hook, a metrics callback) to reduce what our adapter overrides?
11. **Updates and telemetry:** confirm "update notification only, no telemetry" for 1.0.
12. **UI language:** English only for 1.0?
