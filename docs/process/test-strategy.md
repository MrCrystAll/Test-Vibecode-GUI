# Test strategy

Owner: `[QA]`. Applies from 0.1.0 to 1.0.0 and beyond. Changes go through a normal PR reviewed by a developer.
Related: [workflow.md](workflow.md), [roles/tester.md](roles/tester.md), [roadmap](../product/roadmap.md),
per-epic test plans in [docs/qa/](../qa/).

## 1. Principles
1. **Test at the lowest level that can prove the behaviour.** A rule in one function is a unit test; a rule about
   the HTTP contract is an API test; only what needs the real Electron window, the real backend process and the
   real UI together is an e2e test.
2. **Black-box above unit level.** API and e2e tests use only the public contract (HTTP, WS, handshake line, files
   on disk, the UI). They never import app code, so they keep working when internals are refactored and they become
   the contract tests that guard the 1.0 API freeze.
3. **Every acceptance criterion has a named test case** (automated or manual) in the epic's test plan, and
   automated tests carry the ticket key so coverage can be found with `grep`.
4. **CI never needs a GPU, torch, rlgym or rlgym-learn.** Anything that trains uses the fake runner (§9).
   Real rlgym-learn runs are manual tests only, on a machine that has the user's training environment.
5. **Deterministic or it doesn't count.** No sleeps, no dependency on wall-clock speed, network, or the machine's
   installed software beyond the pinned toolchain. A test that fails without a code change is a bug (§8).
6. **Never silently disable a test.** Skips and quarantines are explicit, linked to a Jira Bug, and visible in reports.

## 2. Test levels

| Level | What it proves | Tooling | Written by | Runs in CI |
|---|---|---|---|---|
| Static checks | Lint, format, types, import boundaries, licences, contract drift, commit titles | ruff, mypy/pyright (strict), ESLint, `tsc --noEmit`, import-linter / dependency-cruiser, licence checker, OpenAPI drift script | Developers (story that adds the tool) | Every PR, both OSes |
| Unit — backend | Routes, settings, logging, auth logic, WS envelope, in-process via FastAPI `TestClient`/httpx `ASGITransport` | pytest | Author developer | Every PR, both OSes |
| Unit — adapter / config-schema | Host side (pure Python, no torch); runner side with fakes; schema models and migrations | pytest | Author developer | Every PR, both OSes |
| Unit — UI | Components, services, pipes; the generated client is mocked | Angular test runner chosen in TC-21 (Jest or Karma/Vitest) | Author developer | Every PR, both OSes |
| Unit — desktop | Electron main-process logic: handshake parser, startup state machine, shutdown sequence, PID file | Test runner chosen in TC-23 (Vitest/Jest), Electron APIs stubbed | Author developer | Every PR, both OSes |
| API (black-box) | The backend *as a process*: handshake on stdout, HTTP + WS through the contract, auth, files it writes | pytest + httpx + a WS client, in `tests/api/` (TC-30) | QA (developers may add) | Every PR, both OSes |
| E2E | The desktop app as a user sees it: Electron + backend + UI | Playwright `_electron`, in `tests/e2e/` (TC-29) | QA (developers may add; QA reviews) | Every PR, both OSes (Linux under xvfb) |
| Manual / exploratory | Things automation can't reach cheaply: clean-machine install, real rlgym-learn runs, OS dialogs, visual polish, Task Manager / `ps` checks | Scripted manual test cases in the epic test plan + time-boxed exploratory sessions | QA | No (recorded in the beta report) |

Rough target shape: many unit tests, tens of API tests, a small number of e2e tests per feature (happy path plus
the important failure paths). A behaviour covered by e2e should normally also be covered lower down; the e2e test
proves the wiring, not every branch.

### Definition of done for tests (per story)
- The developer adds unit tests for every new module (CLAUDE.md rule 5) and makes the story's ACs that are
  unit-testable pass in CI.
- QA, while validating the story in **In Test**, adds or extends API/e2e tests for the ACs marked automated in the
  test plan (in a `test/TC-<n>-<slug>` PR) and executes the manual ones. A story can be Done before its QA test PR
  merges only if the manual run passed and the test PR is open; the PR link goes in the Done comment.

## 3. Where tests live

```
apps/backend/tests/                 # backend unit tests (pytest), mirrors src/ layout
packages/rlgym-adapter/tests/       # adapter unit tests; runner-side tests use fakes, never torch
packages/config-schema/tests/       # schema + migration unit tests
packages/contract/                  # contract artefacts (openapi.json, events/*.schema.json) — no tests of its own;
                                    # drift is checked by a script, conformance by tests/api
apps/ui/src/**/*.spec.ts            # Angular unit tests, next to the file under test
apps/desktop/src/**/*.spec.ts       # Electron main/preload unit tests, next to the file under test
tests/                              # QA-owned, black-box; imports nothing from apps/* or packages/*
  api/                              # pytest + httpx suite against a spawned backend (TC-30)
  e2e/                              # Playwright-Electron suite (TC-29)
  fixtures/                         # shared test data (§5)
  support/                          # small helpers shared by api/ and e2e/ (process spawning, temp dirs)
docs/qa/                            # test plans, manual test cases, beta reports
  <version>-test-plan.md
  manual/<area>.md                  # longer manual procedures referenced from a plan
  reports/v<version>-beta.<K>.md    # one sign-off report per beta (from templates/beta-signoff.md)
  templates/
```

`tests/` is its own workspace member (uv for `tests/api`, pnpm for `tests/e2e`) so its dependencies (Playwright,
httpx, websockets) never leak into an app. The one exception to "imports nothing": e2e and API tests may read the
committed contract artefacts in `packages/contract/` (e.g. to validate WS messages against `events/*.schema.json`),
because those are the public contract, not code.

## 4. Naming and traceability

| Kind | File | Test name |
|---|---|---|
| pytest (unit, API) | `test_<module or feature>.py` | `test_<behaviour>_<condition>` e.g. `test_health_returns_ok`, `test_request_without_token_is_401` |
| TS unit | `<file>.spec.ts` | `describe('<Unit>')` / `it('<does something> when <condition>')` |
| E2E | `tests/e2e/specs/<feature>/<behaviour>.spec.ts` | `test('<user-visible outcome>')` |

**Ticket tags.** Tests that verify an acceptance criterion carry the ticket key and AC number:
- pytest: `@pytest.mark.ac("TC-19", 3)` (marker registered in each suite's `conftest.py`/`pyproject.toml`);
- Playwright: `test('…', { tag: ['@TC-29', '@TC-29-AC2'] }, …)`;
- TS unit tests: put `[TC-23 AC6]` at the start of the `describe`/`it` title.

This makes `grep -r "TC-19"` list every test of a story, and lets QA run one story's tests
(`pytest -m ...`, `playwright test --grep @TC-29`). The epic test plan's case IDs (`T-<story>-<n>`) point to these
tests by file and name.

**Selectors.** E2E tests select elements by `data-testid` only (never by CSS class or translated text, since all
strings are externalised and may change). UI developers add `data-testid` to anything a test plan names.

## 5. Test data and fixtures

```
tests/fixtures/
  README.md                         # index: what each fixture is, which version produced it, who uses it
  handshake/                        # sample backend stdout lines (valid, malformed, partial, extra noise)
  contract/                         # sample WS messages, valid and invalid, per event type
  workspaces/<name>/                # (0.2.0+) complete workspace folders, e.g. empty/, one-project/, many-runs/
  migrations/<file-type>/v<N>/      # (0.2.0+) one file per historical schemaVersion; never edited once added
  interpreters/<name>/              # (0.3.0+) fake interpreters: scripts that answer `introspect` like a real env
  entrypoints/<name>/               # (0.3.0+) valid and broken entrypoint modules (non-importable, not spawn-safe…)
  runs/<name>/                      # (0.4.0+) pre-recorded run folders: complete, crashed, checkpoints, pruned
  fake-runner/scenarios/<name>.json # (0.4.0+) fake-runner scripts (§9)
  real-runs/                        # (0.4.0+) small recordings captured from real rlgym-learn runs (JSON only, no .pt/.pkl)
```

Rules:
1. **Fixtures are read-only inputs.** A test copies a fixture into a fresh temp directory (pytest `tmp_path`,
   Playwright per-test temp dir) before using it. Nothing writes inside `tests/fixtures/`.
2. **Every test gets its own temp workspace and its own Electron user-data dir**, created by a shared helper in
   `tests/support/`, deleted on success and kept on failure (path printed, uploaded as a CI artefact).
3. **Paths are hostile on purpose.** Helpers create temp dirs whose names contain a space and a non-ASCII
   character (e.g. `ws é 1`), so path bugs show up on both OSes.
4. **Small and text-only.** Fixtures are JSON/text, a few KB each. Never commit torch files, pickles or checkpoints
   from real runs (they are large and unsafe to load); a recorded real run keeps only its JSON files and logs.
5. **Generated, not hand-edited, where possible.** Fixtures that a tool can produce (e.g. a migration-corpus file for
   the current `schemaVersion`) are produced by a script committed next to them; the README says which.
6. **Migration corpus is append-only.** When a file format gets `schemaVersion` N+1, a `v<N>` sample is added before
   the change merges. Old samples are never edited: they are what users have on disk.
7. **No secrets.** Fixtures and logs never contain real tokens or API keys. Tests use generated tokens.
8. **Per-launch token** for tests is passed by environment variable when a test needs a known token, otherwise read
   from the handshake line like Electron does.

## 6. Platform matrix

| Level | Windows | Linux | Notes |
|---|---|---|---|
| Static + unit | CI `windows-latest` | CI `ubuntu-latest` | Every PR |
| API | CI `windows-latest` | CI `ubuntu-latest` | Every PR |
| E2E | CI `windows-latest` | CI `ubuntu-latest` + xvfb | Every PR; traces and screenshots kept on failure |
| Manual / exploratory | QA machine (Windows 10) for every beta | Linux machine or VM (WSL2 + WSLg acceptable until installers exist) for every beta | Environment recorded in the beta report |
| Clean-machine install (1.0.0) | Fresh Windows VM | Fresh Linux VM | Installer and auto-update checks |
| Real rlgym-learn runs (0.4.0+) | Manual, CPU run of the quick-start template; GPU if available | Manual, CPU run | Never in CI |

Areas where the OSes differ and that every relevant test plan must cover on **both**: process-tree kill (job object /
`taskkill /T` vs process group), `spawn` vs `fork` for env processes, file locking and atomic rename, paths with
spaces / non-ASCII / long paths (> 260 chars on Windows), CRLF vs LF in files the app writes, case-insensitive file
systems, signals vs Windows console events.

## 7. How acceptance criteria map to tests
1. When the PO puts a story in **To Do**, QA adds its rows to the epic test plan: one or more test cases per AC with
   level (Unit / API / E2E / CI / Inspection / Manual) and platforms. Developers can read it before they start.
2. An AC is **Automated** if a test in CI proves it on both OSes, **Manual** if a scripted step in the plan proves it,
   and **Inspection** if it is about a document or file content (QA reads it and records the result).
3. When a story reaches **In Test**, QA validates on the latest `dev` at the story's alpha tag:
   1. full unit suites, API suite and e2e suite are green (CI run on the tag, and locally on Windows);
   2. each test case of the story is executed (or its CI result read) and recorded in the Jira journal;
   3. new API/e2e tests for the story are added in a `test/TC-<n>-<slug>` PR.
4. **Pass** → Done with `[QA] PASSED on <tag>` listing the test cases and how they were checked.
   **Fail** → a Bug per distinct failure, linked to the story ("is caused by" / "relates to"), the story goes back to
   **In Progress** with `[QA] FAILED`, and the author developer gets a message.

### Bug reports
Title `[<area>] <what is wrong>`. Body: environment (OS, tag/commit), steps, expected, actual, logs/screenshots/traces,
linked story, severity. Fix version = the epic being stabilised.

| Severity | Meaning | Blocks a beta sign-off? |
|---|---|---|
| Blocker | App unusable, data loss, security hole (e.g. token leak, auth bypass), orphaned processes | Yes |
| Critical | An AC or exit criterion fails; no workaround | Yes |
| Major | Feature works with a workaround, or fails on one OS in a non-core path | Yes, unless the PO defers it in writing in the Bug |
| Minor / Trivial | Cosmetic, wording, rare edge case | No |

## 8. Flaky-test policy
- A test is **flaky** when it both passes and fails on the same commit. Playwright's report marks pass-on-retry as
  flaky; for other suites, any unexplained red that passes on rerun counts.
- **Retries:** unit and API suites: none. E2E: at most 1 retry, CI only, so a flake doesn't block unrelated PRs;
  every pass-on-retry is still reported as flaky in the CI summary and must be acted on.
- **Every flake becomes a Bug** (label `flaky`, linked to the story whose test it is), filed by whoever sees it,
  with the CI run link and trace. Nobody reruns CI "until green" without filing it.
- **Quarantine, never delete or skip silently.** If a flaky test blocks the team, QA may tag it `@quarantine`
  (Playwright) / `@pytest.mark.quarantine` with the Bug key in the reason. Quarantined tests still run in a
  non-blocking CI job, are listed in every beta report, and are fixed or replaced within the same epic. A beta
  cannot be signed off with a quarantined test covering one of the epic's exit criteria.
- Common causes to check first: sleeps instead of waiting for a condition, shared temp dirs or ports, tests depending
  on order, real wall-clock time, leftover processes from an earlier test.

## 9. Fake runner (requirements for 0.4.0 A5, used from 0.3.0 for fake interpreters)
The fake runner lets the UI, API tests, e2e tests and CI exercise the whole run lifecycle without torch, rlgym, a
GPU or rlgym-learn. It lives on the adapter's runner side (developer-owned); QA owns its scenarios and fixtures.
It must be **indistinguishable from the real runner through every public surface the studio uses**: if the backend
needs a code path that only works with the fake, that is a bug.

**Must emulate**
1. **Launch contract:** started by the backend exactly like the real runner (same command-line/entrypoint shape, cwd
   = run folder, env vars such as `OPENBLAS_NUM_THREADS=1`), runs on the plain Python stdlib.
2. **Structured events:** the same event types, schemas and order as the real runner — started, heartbeat, paused,
   resumed, checkpoint-saved, stopped, completed, crashed (with traceback) — on the same channel.
3. **stdout/stderr:** realistic log lines, including the upstream markers the backend may key on
   (`Learning coordinator successfully initialized!`, `Hit timestep limit, cleaning up...`,
   `LEARNING LOOP ENCOUNTERED AN ERROR` + traceback, `FAILED TO SAVE ON EXIT`), ANSI colour codes and long lines,
   written to `logs/stdout.log`.
4. **Files on disk:** the real layout — `config.json`, `shmem_flinks/`,
   `<agent_controller_save_folder>/[<subcontroller>/]<run_name><run_suffix>/<time_ns>/…` with JSON files with the
   real names (`ppo_agent.json` written **last**, `ppo_learner/misc.json`, `trajectory_processor.json`) and
   small placeholder files for `.pt`/`.zip`/`.pkl`; pruning to `n_checkpoints_to_keep`; multi-controller subfolders.
5. **Metrics (0.5.0):** `metrics.jsonl` records in format v1, one per iteration per controller, with the default PPO
   metric names plus nested custom metrics; values are deterministic from a seed.
6. **Control channel:** accepts the same commands as the real runner (pause, resume, checkpoint now,
   stop-with-checkpoint, add/remove env process, change min-frac) with a configurable acknowledgement delay that
   mimics the 50-iteration `process_kbhit` polling.
7. **Process tree:** spawns N real child "env" processes (sleeping stubs) so process-tree kill, orphan cleanup and
   env-process counts are tested for real on Windows and Linux; can lose a child to emulate an env-process crash.
8. **Exit semantics:** exit codes and final events matching the table in the integration notes §3 (completed,
   stopped, crashed, init failure).
9. **Resume:** loads from `checkpoint_load_folder` and continues `cumulative_timesteps` while restarting the
   timestep-limit counter at 0, as upstream does.
10. **Time control:** a speed factor (iterations per second) so a "long" run takes seconds in CI, and a
    step mode where the test advances iterations explicitly, for fully deterministic e2e.
11. **Introspection (0.3.0, as a fake interpreter):** answers `introspect` with configurable Python / rlgym /
    rlgym-learn / algos / torch / CUDA versions and devices, and returns a fixed config JSON Schema with defaults
    (single-agent PPO, multi-agent, wandb variants).

**Fault injection** (selected by scenario file in `tests/fixtures/fake-runner/scenarios/`): init failure before the
"initialized" marker; crash at iteration N; checkpoint save fails; a checkpoint left half-written (no
`ppo_agent.json`); env process dies; heartbeat stops (stall) while the process stays alive; process ignores the
stop command (forces kill path); garbage or truncated event lines; very fast metrics bursts; and, for 0.8.0, the
messages of each classified error (import error, CUDA unavailable, OOM, serde/space mismatch, entrypoint not
spawn-safe, config validation).

**Parity check:** every epic that changes the runner includes one manual real-run test whose event stream and file
tree are compared with the fake runner's for the same scenario; differences are Bugs against the fake runner. Small
JSON/log recordings from these runs go to `tests/fixtures/real-runs/`.

## 10. Betas and regressions
1. When every story of epic `0.N.0` is Done, QA tags `v0.N.0-beta.1` on `dev` (with `tools/tag-prerelease` once
   TC-27 lands; until then by hand following the lookup rule in workflow.md) and pushes the tag.
2. **Full regression on the beta tag**, recorded in `docs/qa/reports/v0.N.0-beta.K.md` from
   [templates/beta-signoff.md](../qa/templates/beta-signoff.md):
   - all CI jobs green on Windows and Linux for the tagged commit;
   - all automated suites, including e2e for every previous epic (the regression suite is the whole automated suite;
     there is no reduced subset), plus a list of quarantined tests;
   - every manual test case of the epic's plan, on Windows and on Linux;
   - the manual cases of earlier epics marked *regression* in their plans;
   - a time-boxed exploratory session (≥ 30 min per OS) on the epic's features, notes in the report;
   - for 0.2.0+: open the previous release's data with the beta (migration corpus + one real workspace).
3. Bugs found during stabilisation are fixed on `dev` through normal `fix/` PRs; each fix merges as the next beta
   (`beta.2`, …). On a new beta QA reruns all automated suites, the manual cases for the touched areas, and the smoke
   checklist; the report records what was rerun.
4. **Sign-off** when no Blocker/Critical/undeferred Major bug is open for the epic and every exit criterion passed on
   both OSes. QA then messages the supervisor with the report link; the supervisor opens the release PR to `main`.
   If sign-off is not possible, QA reports the blocking Bugs instead.
5. After the release tag `v0.N.0`, QA reruns the e2e smoke test on the `main` commit as a final check.

## 11. Reports and journal
- The Jira journal (comments on the ticket) holds what was verified, how, and on which tag. Tooling and environment
  problems are written as `[QA] STRUGGLING: …` as soon as they cost more than one failed attempt.
- CI keeps Playwright traces, screenshots and backend logs of failed tests as artefacts.
- Beta reports live in `docs/qa/reports/` and are committed through a `test/` PR so they are reviewable history.
