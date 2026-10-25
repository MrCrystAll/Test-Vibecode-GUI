# ADR-0004: Two-sided rlgym adapter (host side and runner side)

- Status: Proposed (2026-10-25)
- Ticket: TC-12

## Context
A training run is defined by two things: a config (data, `LearningCoordinatorConfigModel` JSON) and code (the user's
env factory, agent controller, models and rewards). Only the user's own Python environment can build the code half,
and the full config schema depends on that code (integration notes §1, §7). The owner decided that **the backend
ships with its own bundled Python and never imports torch** (ADR-0005), that **rlgym-learn is reached only through the
adapter** (CLAUDE.md rule 3), and that **introspection runs in the user's interpreter**, so the studio and the
training environment can never disagree on versions.

Upstream facts that shape the design (integration notes §3):
- Run control is keyboard-only (`process_kbhit` reads console keys through `msvcrt` / `termios`). This does not work in a
  child process started by a GUI, so the studio must replace it.
- Exit codes are not meaningful (`start()` swallows exceptions), so status must come from the runner itself.
- User code and rlgym-learn print freely to stdout (metrics dicts, banners, tracebacks), and env processes inherit it.
- All relative paths resolve against the child's cwd; Windows uses `spawn` for env processes.
- Upstream already broke its API between versions (2.0.0 rewrote agent controllers).

## Decision

### 1. Two sides, one package
`packages/rlgym-adapter` is one Python distribution (`studio-rlgym-adapter`) with one top-level import package,
`studio_rlgym_adapter`, split into three subpackages with strict import rules:

| Subpackage | Runs in | May import | Must not import |
|---|---|---|---|
| `protocol` | both | stdlib only | anything else |
| `host` | the backend's bundled Python | stdlib, `protocol`, the backend's own light deps (e.g. pydantic) | `runner`, torch, rlgym, rlgym-learn, rlgym-learn-algos, wandb, mlflow |
| `runner` | the **user's** training interpreter (Python >= 3.10) | stdlib, `protocol`, and the user's installed libraries (rlgym, rlgym-learn, algos, torch, sinks) | `host`, anything that is neither stdlib nor in the user's environment |

- **Host side** (used by the backend): builds launch specs, starts and stops runner processes, reads runner output
  files, parses events, knows the run folder layout. Pure Python, no torch or rlgym anywhere in its import graph.
- **Runner side** (runs in the user's interpreter): loads the user's entrypoint, injects the studio-owned config,
  replaces keyboard control, writes events (and later metrics), answers introspection. It imports torch, rlgym and
  rlgym-learn **lazily, inside functions**, so it can still start and report "torch is missing" or "unsupported
  rlgym-learn version" as a structured error instead of crashing with an `ImportError` at import time.
- **Protocol** holds the message envelope, event and command names and the protocol version as plain dataclasses and
  dicts, so both sides agree without either importing the other.
- The backend imports `studio_rlgym_adapter.host` and `studio_rlgym_adapter.protocol` only. Nothing else in the
  repository imports rlgym-learn.

**How the runner reaches the user's interpreter without being installed there.** The studio never installs anything
into the user's environment. The host starts the user's interpreter with the adapter's source root prepended to
`PYTHONPATH`. That directory contains only `studio_rlgym_adapter/` (src layout), and the package `__init__` imports
nothing. In dev this is `packages/rlgym-adapter/src`; in packaged builds the ADR-0005 bundle build copies the same
tree to `<resources>/backend/runner/`. It is never the bundled `site-packages`, which would leak the backend's own
dependencies (such as its pydantic version) into the user's process. The user's interpreter is started without `-I`,
so the user's venv, conda env and `PYTHONPATH` keep working.

### 2. Launch contract
```
<user python> -u -m studio_rlgym_adapter.runner <command> --spec <absolute path to spec.json>
```
- `<command>` is `introspect` (0.3.0), `check-entrypoint` (0.3.0) or `run` (0.4.0). New commands are additive.
- `spec.json` is written by the host before launch: protocol version, run folder, entrypoint (contract specified in
  0.3.0), resolved upstream config, output file paths. All paths in it are absolute.
- cwd = the run folder (or a temp folder for one-shot commands), because upstream resolves `config.json`,
  `agent_controller_save_folder`, `flinks_folder` and wandb's folder against cwd.
- Environment: `PYTHONPATH` as above, `PYTHONUNBUFFERED=1`, `PYTHONIOENCODING=utf-8`, `OPENBLAS_NUM_THREADS=1`
  (upstream's recommendation). No secrets on the command line.
- The **fake runner** (0.4.0 A5) is `studio_rlgym_adapter.runner.fake`, launched with exactly the same command shape,
  spec file and channels, using the stdlib only, so CI and e2e never need torch, rlgym or a GPU.

### 3. Channels
Each channel has one job, so user prints can never corrupt studio data:

| Direction | Channel | Carries |
|---|---|---|
| host → runner, at start | `spec.json` (file) + argv + env vars | everything the runner needs to start |
| host → runner, live | the runner's **stdin**, one JSON object per line | control commands (pause, resume, checkpoint, stop, add/remove env process, step min-frac up/down) |
| runner → host, live and durable | **append-only JSONL files** in the run folder's studio area: `events.jsonl` now, `metrics.jsonl` in 0.5.0 | structured events: hello, started, heartbeat, paused, resumed, checkpoint-saved, command-ack, stopped, completed, crashed, error |
| runner → host, one-shot | a **result JSON file** named in the spec, written atomically (temp file + rename) | introspection and check-entrypoint results |
| runner → host, human | stdout + stderr, captured by the host to `logs/stdout.log` | free text from the user, upstream and the runner. Never parsed for control flow; upstream markers (e.g. `LEARNING LOOP ENCOUNTERED AN ERROR`) may only serve as hints for the error classifier (0.8.0) |

- Every structured line uses one envelope: `{"v": <protocol major>, "type": ..., "seq": <n>, "ts": <ISO-8601 UTC>,
  "payload": {...}}`. The first event is `hello`, with the runner's protocol version, Python version and upstream
  versions; the host refuses an incompatible major version.
- The host tails `events.jsonl` by byte offset and reads complete lines only. Files make events durable and
  replayable: the backend can rebuild a run's state after its own restart, QA can use recorded fixtures, and the
  format fits ADR-0002. Iterations take seconds, so a polling tail (about 200 ms) is fast enough.
- **stdin EOF means the host is gone**: the runner then stops with a checkpoint, so a crashed backend does not leave a
  training run going headless. Hard kill of the process tree (job object / process group, 0.4.0 A3) remains the
  fallback for a runner that does not respond.
- **Rejected:**
  - events on stdout with a sentinel prefix: user and env-process prints interleave with them, and line atomicity of
    concurrent writers is not guaranteed on Windows pipes;
  - a local TCP socket: one more listening port to authenticate, Windows firewall prompts, more code. Revisit only if
    file tailing ever proves too slow;
  - an extra inherited pipe: handle inheritance differs between Windows and POSIX.

### 4. Run control through a `process_kbhit` override
The runner subclasses upstream's `LearningCoordinator` and overrides `process_kbhit(self, kb) -> bool` (in 2.0.x,
returning `True` ends the learning loop). It never reads the console; the `KBHit` object passed in is ignored. A
background thread reads command lines from stdin into a queue, and each `process_kbhit` call:
1. drains the queue and maps each command onto the upstream action its key triggers (`c` checkpoint via
   `agent_controller.save_checkpoint()`, `q` checkpoint then return `True`, `a`/`d` add/delete one env process,
   `j`/`l` step min-frac up/down), then writes a `command-ack` event with the command id;
2. implements **pause** itself: it stays in the call, writes `paused` and heartbeat events and keeps draining commands
   until `resume` or `stop` arrives (upstream's own pause waits for a key press, which cannot happen here);
3. writes a `heartbeat` event (timesteps, env process count, paused flag).

Upstream polls `process_kbhit` every 50 loop iterations, so commands are not instantaneous; the UI shows them as
pending until their `command-ack`. The exact upstream calls are pinned per supported version (§6).

### 5. Introspection always runs in the user's interpreter
Versions (Python, rlgym, rlgym-learn, rlgym-learn-algos, torch, wandb), devices (CUDA availability and device list,
which needs `import torch`) and the **concrete config JSON Schema with defaults** (which needs the user's components,
because nested configs are typed by each component's `config_model`) are produced only by `runner introspect`, in the
interpreter that will train. The backend never computes, guesses or bundles any of them. The host may cache results,
keyed by interpreter path and the package versions it reported, and drops the cache when either changes.

### 6. Supported upstream versions
| Library | Supported | Notes |
|---|---|---|
| rlgym-learn | 2.0.x | 1.x is out of scope (roadmap) |
| rlgym-learn-algos | 0.4.x | |
| rlgym | >= 2, as required by rlgym-learn 2.0.x | generic RLGym v2 API only |

- The runner checks installed versions first (`importlib.metadata`, without importing torch) and reports an
  `unsupported-version` error naming the found and the supported versions. It never "tries anyway".
- Version-specific upstream calls (the coordinator subclass, the key-to-action mapping, the checkpoint layout reader)
  live in one module per supported upstream line under `runner/compat/`, selected at start-up.
- **Adding support for a new upstream version is a story**: study the upstream diff in `.reference/` (read only), add
  or adapt the `compat` module, update the fake runner if the event stream or file layout changes, record a real-run
  fixture (JSON and logs only), and update the table above and the supported-version matrix (0.3.0 A5). Until that
  story is Done, the new version is reported as unsupported.

### 7. Environment-agnostic core
The adapter, backend and UI depend only on the generic RLGym v2 API and rlgym-learn. Nothing outside project
templates may import or reference Rocket League-specific packages (`rlgym.rocket_league`, RocketSim, rlviser) or
assume Rocket League concepts. The Rocket League quick-start is one template among others (owner decision). Templates
live in their own folder, chosen by the template story (0.3.0 B3), and are user code that the runner runs like any
other entrypoint. `render` / `render_delay` are passed through as plain config.

### 8. How the boundaries are enforced
The import-boundary lint story (TC-25) implements these checks, runnable locally with one command and in CI:
- **Static import contracts** over the Python sources (e.g. `import-linter`): `torch`, `rlgym`, `rlgym_learn`,
  `rlgym_learn_algos`, `wandb` and `mlflow` are forbidden everywhere except in `studio_rlgym_adapter.runner`;
  `studio_rlgym_adapter.host` and `apps/backend` must not import `studio_rlgym_adapter.runner`;
  `studio_rlgym_adapter.protocol` may import the stdlib only; no package imports `apps/*` (ADR-0001). Each rule has a
  failing fixture in the lint's own tests.
- **Dependency check** (TC-17 AC6): the backend's resolved dependency tree contains none of torch, rlgym, rlgym-learn
  and rlgym-learn-algos. None of them is ever a declared dependency of any package in this repository.
- **Runtime check**: a backend unit test imports the application and asserts that none of those modules is in
  `sys.modules`, which also catches dynamic imports that static analysis misses.
- **Bundle guard** (ADR-0005, 0.8.0): the bundle build fails if any of those packages is found in the bundle.

## Consequences
- The backend stays small, CUDA-free and independent of the user's training stack, and the user's environment stays
  untouched (nothing is installed into it).
- Every upstream change is absorbed in `runner/compat/` and the supported-version table; other code does not move.
- The runner side must stay compatible with Python 3.10+ and use only the stdlib plus what the user's environment
  already has, so it cannot use the backend's libraries; shared types live in `protocol` as plain data.
- File-based events give durability and replay for free, at the cost of a few hundred milliseconds of latency and some
  care with partial lines and file sharing on Windows.
- The fake runner implements the same launch contract and channels, so everything except real training is testable in
  CI on Windows and Linux.
- The protocol (`spec.json`, events, commands) becomes part of the public surface frozen at 1.0.0 (roadmap 0.9.0 A3).
- The entrypoint contract (the `build()` module) is specified in 0.3.0 and plugs into the `spec.json` / `runner`
  design above.
