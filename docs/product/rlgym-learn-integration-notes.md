# rlgym-learn integration notes

Owner: `[PO]`. Audience: developers building the backend, the rlgym adapter and the config editor.
Studied (read-only, never executed) on 2026-10-25:

| Library | Version | Commit |
|---|---|---|
| [JPK314/rlgym-learn](https://github.com/JPK314/rlgym-learn) | 2.0.0 (2026-08-29) | `2503793` |
| [JPK314/rlgym-learn-algos](https://github.com/JPK314/rlgym-learn-algos) | 0.4.2 (2026-09-05) | `466b8e3` |

Both are Python + Rust (PyO3/maturin), Python `>=3.10,<=3.14`, pydantic v2 for every config model. rlgym-learn
depends on `rlgym>=2`; algos depends on `torch` and optionally `wandb`. Upstream already breaks APIs between versions
(2.0.0 rewrote the agent-controller API), so **pin the supported versions in the adapter and treat upgrades as stories.**

File/line pointers below are relative to the clone roots in `.reference/`.

---

## 1. Mental model

```
user's training script (Python, user's own venv)
 └─ LearningCoordinator(env_create_function, agent_controller, config | config_location)
     ├─ EnvProcessInterface (Rust) ── spawns N env processes (multiprocessing, "spawn" on Windows)
     │     each process calls env_create_function() → rlgym.api.RLGym (obs builder, reward fn, action parser,
     │     done conditions, state mutators, transition engine e.g. RocketSim)
     └─ AgentController (one; may be a MultiAgentController with named subcontrollers)
           PPOAgentController = PPOLearner (actor-critic + optimizers)
                              + ExperienceBuffer (+ TrajectoryProcessor, e.g. GAE)
                              + MetricsLogger (e.g. WandbMetricsLogger(PPOMetricsLogger()))
                              + optional ObsStandardizer
```

**The single most important fact for the product:** a run is defined by *two* things, and only one of them is data.

1. **Config (data)** — a JSON file validated into `LearningCoordinatorConfigModel` (hyper-parameters, process
   counts, devices, logging, checkpoint folders). This is what the GUI can edit as forms.
2. **Code (Python callables)** — `env_create_function`, `actor_critic_factory`, `optimizers_factory`, the reward
   functions/obs builders inside the env, the choice of experience buffer / metrics logger / obs standardizer classes,
   and any custom `AgentController`. These are *constructor arguments*, not config. They cannot be expressed in JSON.

So the studio cannot "be" the training script. It must **launch a user-provided Python entrypoint** that builds the
code half, while the studio owns and injects the config half. Defining that entrypoint contract is an extension point
and part of the 1.0 public API (see §8).

A second consequence: **the shape of the config depends on the code.** Nested configs (`agent_controller_config`,
`metrics_logger_config`, `trajectory_processor_config`, `subcontrollers_config`, `inner_metrics_logger_config`) are
typed `AnyBaseModel` (JSON schema `{"type": "object"}`) and are validated in `model_validator(mode="before")` using the
*live component instance* passed as pydantic `context` (each component exposes a `config_model` property).
Example: `learning_coordinator_config.py:58-95`, `ppo/ppo_agent_controller.py` (`validate_metrics_logger_and_experience_buffer_config_models`).
→ A complete JSON schema for a project can only be produced by instantiating (or at least importing) the user's
components. Schema generation must therefore run **inside the user's Python environment** (see §7).

---

## 2. Config surfaces (everything a GUI must be able to edit)

Defaults in parentheses. All models are `extra="forbid"`, so unknown keys fail validation.

### 2.1 `LearningCoordinatorConfigModel` — `python/rlgym_learn/learning_coordinator_config.py`
| Field | Type (default) | Notes |
|---|---|---|
| `base_config` | `BaseConfigModel` (required) | §2.2 |
| `process_config` | `ProcessConfigModel` | §2.3 |
| `agent_controller_config` | `AnyBaseModel \| None` (None) | Shape given by the agent controller's `config_model` (§2.4 / §2.9) |
| `agent_controller_save_folder` | str (`"agent_controller_checkpoints"`) | Root of all checkpoints. Upstream comment: *"THIS PROCESS MAY DELETE ANYTHING INSIDE THIS FOLDER"* (checkpoint pruning). |

Written to disk by `generate_config()` with `model_dump_json(indent=4, polymorphic_serialization=True)`; default
filename `config.json` in cwd. `generate_config` calls `input()` if the file exists and `force_overwrite=False` →
**never let it prompt in a headless child process** (always pass `force_overwrite=True` or don't call it).

### 2.2 `BaseConfigModel` — `python/rlgym_learn/basic_config.py`
| Field | Default | Notes |
|---|---|---|
| `serde_types` | required | `SerdeTypesModel`: `agent_id_serde_type`, `obs_serde_type`, `action_serde_type`, `reward_serde_type`, `obs_space_serde_type`, `action_space_serde_type` (required); `shared_info_serde_type`, `shared_info_setter_serde_type`, `state_serde_type` (optional). Values are `PyAnySerdeType` trees (e.g. `NUMPY(np.float64)`, `TUPLE((STRING(), INT()))`). Pydantic-serialisable (pyany_serde 0.6.1 has JSON-schema support). Advanced; must match the env's types. |
| `random_seed` | 123 | |
| `shm_buffer_size` | 16384 | Shared-memory buffer per env process (bytes). |
| `flinks_folder` | `"shmem_flinks"` | Shared-memory file links. **Relative to cwd.** |
| `timestep_limit` | 5 000 000 000 | Stop condition. Counted by the coordinator from 0 at every start — **not restored on resume** (`learning_coordinator.py`: `self.cumulative_timesteps = 0`). |

### 2.3 `ProcessConfigModel` — `basic_config.py`
| Field | Default | Notes |
|---|---|---|
| `n_proc` | 8 | Env processes. Can change live via terminal keys `a`/`d`. |
| `min_frac_process_responses_per_collection` | 0.45 | In [0,1]. Live-adjustable via `j`/`l`. |
| `render` | False | Renders env process 0 (rlviser for Rocket League; separate app the user installs). |
| `render_delay` | None | Seconds between rendered frames. |
| `launch_delay` | None | Seconds between process spawns. |
| `recalculate_agent_id_every_step` | False | PPOAgentController asserts this is False. |

### 2.4 `PPOAgentControllerConfigModel` — algos `ppo/ppo_agent_controller.py`
| Field | Default | Notes |
|---|---|---|
| `timesteps_per_iteration` | 50 000 | One learning iteration = one metrics report. |
| `save_every_ts` | 1 000 000 | Checkpoint cadence (checked after each iteration). |
| `run_name` | `"rlgym-learn-run"` | Checkpoint folder = `run_name + run_suffix`. |
| `run_suffix` | `-{time.time_ns()}` **at model construction** | Freezes into config.json when generated. The studio should set it explicitly. |
| `checkpoint_load_folder` | None | Path to a specific checkpoint dir (`…/<run>/<time_ns>`) to resume/fine-tune from. |
| `n_checkpoints_to_keep` | 5 | Older checkpoint dirs are `shutil.rmtree`'d. |
| `random_seed` | 123 | |
| `save_mid_iteration_data_in_checkpoint` | True | Pickles partial-iteration trajectories. |
| `learner_config` | §2.5 | |
| `experience_buffer_config` | §2.6 | |
| `metrics_logger_config` | None | Shape given by the metrics logger's `config_model` (§2.8). |

### 2.5 `PPOLearnerConfigModel` — algos `ppo/ppo_learner.py`
`dtype` (torch.float32, serialised as string), `n_epochs` (1), `batch_size` (50 000), `n_minibatches` (1),
`ent_coef` (0.005), `clip_range` (0.2), `max_grad_norm` (0.5 | None),
`optimizer_named_parameter_group_kwargs` (`{"actor": {"lr": 3e-4}, "critic": {"lr": 3e-4}}` — free-form dict whose keys
are interpreted by the user's `optimizers_factory`), `advantage_standardization` (True), `device` (`"cpu"`, e.g.
`"cuda:0"`), `cudnn_benchmark_mode` (True, forced False off-CUDA).
On resume, optimizer kwargs from config override those stored in the checkpoint → **learning rate can be changed
between resumes**, a useful GUI feature.

### 2.6 `ExperienceBufferConfigModel` — algos `ppo/experience_buffer.py`
`max_size` (100 000), `device` ("cpu"), `save_experience_buffer_in_checkpoint` (True),
`trajectory_processor_config` (generic; §2.7). Implementations: `ExperienceBuffer` (torch) and `NumpyExperienceBuffer`.

### 2.7 `GAETrajectoryProcessorConfigModel` — algos `ppo/gae_trajectory_processor.py`
`gamma` (0.99), `lmbda` (0.95), `standardize_rewards` (True), `max_returns_per_stats_increment` (None),
`reward_clip` (10 | None). Implementations: Rust `GAETrajectoryProcessor` and pure-Python variant.

### 2.8 Metrics logger configs — algos `logging/`
- `PPOMetricsLogger` (a `DictMetricsLogger`): `config_model = None`, prints a nested dict each iteration.
- `WandbMetricsLoggerConfigModel`: `inner_metrics_logger_config` (required, may be null), `enable` (True), `project`,
  `group`, `run`, `id` (None; resumes that wandb run), `new_run_with_run_suffix` (False), `additional_wandb_run_config`
  (dict), `settings_kwargs` (dict → `wandb.Settings`). Wraps an inner `DictMetricsLogger` and logs its flattened dict
  (`"PPO Metrics/Critic Loss"` style keys). Run id is persisted in the checkpoint for resume.

### 2.9 `MultiAgentControllerConfigModel` — algos `agent_controller/multi_agent/multi_agent_controller.py`
`subcontrollers_config: dict[name, config | None]`; every subcontroller registered in code must have a key.
Subcontrollers (e.g. several `PPOAgentController`s for self-play vs. a frozen opponent) each get their own save folder
`<agent_controller_save_folder>/<subcontroller_name>/…` and their own metrics logger. **The GUI must handle N agent
controllers per run, keyed by name.**

### 2.10 Code-level surfaces (not JSON; exposed through the entrypoint contract)
Env: state mutators, obs builder, action parser, reward function (often `CombinedReward((fn, weight), …)`), termination
/ truncation conditions, transition engine. Model: actor/critic architecture (`DiscreteFF`, `ContinuousActor`,
`BasicCritic`, `SeparateActorCritic`, layer sizes), optimizers. Optional `NumpyObsStandardizer`.
The studio can *display* and later *parameterise* these (e.g. reward weights, layer sizes) only if the entrypoint
reads them from a studio-provided parameters file — a candidate post-1.0 / late-0.x feature, not something to infer.

---

## 3. Launching and stopping a run

### Launch
`LearningCoordinator(env_create_function, agent_controller, config=… | config_location=…)` then `.start()`
(`python/rlgym_learn/learning_coordinator.py`). The constructor spawns all env processes, calls
`agent_controller.set_space_types` then `.load(...)` (which builds models and loads checkpoints). `start()` runs the loop
until `timestep_limit`, `q`, an exception, or no env left; on exception/KeyboardInterrupt it **saves a checkpoint**,
then cleans up processes.

Constraints for the studio's runner:
- **Windows uses `spawn`** (forkserver only where available). `env_create_function` must be a picklable module-level
  callable, and the entry module must be import-safe (`if __name__ == "__main__":` guard).
- **All relative paths resolve against the child's cwd** (`config.json`, `agent_controller_save_folder`,
  `flinks_folder`, wandb's `./wandb`). The runner must set cwd to the run folder or write absolute paths.
- Set `OPENBLAS_NUM_THREADS=1` in the child env (upstream does this in its examples to avoid env processes throttling
  each other).
- The process tree is: runner → N env processes (+ rlviser if rendering). Stopping must kill the whole tree
  (Windows: job object / `taskkill /T`).
- The child needs the user's Python with `rlgym`, `rlgym-learn`, `rlgym-learn-algos`, `torch` (CUDA build if GPU),
  optionally `wandb`, plus Rust only if wheels are unavailable. The studio must **not** bundle these; it selects an
  interpreter / venv per project and validates it (§7).

### Live control (today: keyboard only)
`process_kbhit` is polled every 50 loop iterations and reads **raw console keys** (`msvcrt` on Windows, `termios` on
POSIX — `util/kbhit.py`): `p` pause (any key resumes), `c` checkpoint, `q` checkpoint + quit, `a` add env process,
`d` delete env process, `j`/`l` change `min_frac_process_responses_per_collection`.
**This does not work for a GUI-spawned child**: `msvcrt` reads the console, not stdin, and without a TTY on POSIX
KBHit disables itself. Ctrl-C delivery to a console-less child on Windows is also unreliable.
→ The adapter's runner should subclass `LearningCoordinator` and override `process_kbhit(kb)` to read commands from a
control channel (local socket, named pipe, or a polled `control.json` in the run folder) and map them to the same
actions. This gives graceful **pause / resume / checkpoint now / stop with checkpoint / add-remove env process**.
Hard kill is the fallback (no final checkpoint; last periodic checkpoint survives).
Note the 50-iteration polling granularity: commands are not instantaneous.

### Exit semantics to surface
| Outcome | How detected |
|---|---|
| Completed (timestep limit) | stdout `"Hit timestep limit, cleaning up..."`, exit code 0 |
| Stopped by user | our control command acknowledged, exit 0 |
| Crashed | stdout `"LEARNING LOOP ENCOUNTERED AN ERROR"` + traceback; checkpoint attempted (`"FAILED TO SAVE ON EXIT"` if that also failed) |
| Init failure | exception before "Learning coordinator successfully initialized!" (bad config, bad interpreter, CUDA missing) |
| Env process crash | reported to the controller as `EnvCloseReason.EXCEPTION`; PPO controller ignores it → run continues with fewer envs |

Exit codes are not meaningful upstream (exceptions are swallowed by `start()`), so the runner must emit its own
structured status events.

---

## 4. What a run writes to disk

```
<cwd>/
  config.json                         # if generate_config() is used
  shmem_flinks/                       # shared-memory links (transient; safe to delete when no run is alive)
  wandb/                              # if wandb is enabled (wandb's own local run dir)
  <agent_controller_save_folder>/
    [<subcontroller_name>/]           # only with MultiAgentController
      <run_name><run_suffix>/         # one per run
        <time_ns>/                    # one per checkpoint; folder name = wall-clock ns, sortable
          ppo_learner/actor_critic.pt   # torch state_dict (model weights)
          ppo_learner/optimizers.pt
          ppo_learner/misc.json         # {"cumulative_model_updates": n}
          experience_buffer/experience_buffer.zip   # pickles inside (large: obs × max_size)
          experience_buffer/trajectory_processor.json  # GAE running stats
          metrics_logger/wandb_metrics_logger.json     # {"run_id": ...} (if wandb)
          metrics_logger/inner_metrics_logger/
          iteration_trajectories.pkl    # if save_mid_iteration_data_in_checkpoint
          iteration_shared_infos.pkl
          ppo_agent.json                # {cur_iteration, iteration_timesteps, cumulative_timesteps, ...} — WRITTEN LAST
```
Facts that matter:
- **Checkpoint completeness:** `ppo_agent.json` is the last file written by `save_checkpoint` → treat its presence as
  "checkpoint complete" when watching the folder.
- **Pruning crashes on foreign files:** pruning does `int(name)` for every entry of the run folder. **The studio must
  never write anything inside `<run_name><run_suffix>/`** (no metadata, no thumbnails). Keep studio metadata beside
  it, not in it.
- Checkpoints contain pickles and torch files → loading = arbitrary code execution. Only load checkpoints the user
  trusts; the studio itself should read only the JSON files.
- `cumulative_timesteps` in `ppo_agent.json` is the true training progress across resumes (unlike `timestep_limit`).
- Legacy conversion: `rlgym_learn_algos.conversion.convert_rlgym_ppo_checkpoint` converts rlgym-ppo checkpoints
  (`PPO_POLICY.pt` …) — a possible import feature.

## 5. Metrics — what exists and how to observe it live

Per **iteration** (every `timesteps_per_iteration`), `PPOAgentController._learn()` builds `PPOAgentControllerData`
and calls `metrics_logger.collect_agent_metrics`, `collect_env_metrics(shared_infos)`, `report_metrics()`.
`PPOMetricsLogger.get_metrics()` returns:

- **Timing:** PPO Batch Consumption Time, Total Iteration Time, Timestep Collection Time, Timestep Consumption Time,
  Collected Steps per Second, Overall Steps per Second
- **Timestep Collection:** Cumulative Timesteps, Timesteps Collected
- **PPO Metrics:** Average Reward, Average Undiscounted Episodic Return, Average Return, Return Standard Deviation,
  Cumulative Model Updates, Actor Entropy, Mean KL Divergence, Critic Loss, SB3 Clip Fraction, Actor Update Magnitude,
  Critic Update Magnitude
- **Custom env metrics:** users subclass `PPOMetricsLogger.collect_env_metrics` to aggregate `shared_info` dicts
  sent from env processes (requires `shared_info_serde_type`). Arbitrary nested dicts → the GUI must render
  **arbitrary nested numeric metrics**, not a fixed list.

Observation options (none is built in; today metrics go to stdout and/or wandb):
1. **Recommended — studio metrics logger (adapter-provided):** a `MetricsLogger` decorator, like `WandbMetricsLogger`,
   that wraps the user's inner `DictMetricsLogger`, appends one JSON line per iteration to
   `<studio run folder>/metrics.jsonl` (`{"iteration", "cumulative_timesteps", "wall_time", "controller", "metrics": {...}}`),
   and still delegates `report_metrics()`. It can wrap or sit beside wandb. The backend tails the file and pushes over
   WebSocket. File-based → survives backend restarts, replayable, matches ADR-0002.
2. Parse stdout (`print_dict` output) — fragile, fallback only.
3. Read from wandb — remote service, not a dependency we want.

Iteration cadence is coarse (often tens of seconds). For "is it alive" between iterations, the runner should emit a
heartbeat (timesteps collected, n_procs, paused) from the overridden `process_kbhit` hook.

## 6. Checkpoints — live observation and actions
- Watch `<agent_controller_save_folder>/**/<run>/` for new `<time_ns>` folders; mark complete when `ppo_agent.json`
  exists; read it for iteration/timesteps.
- Expect folders to disappear (pruning, `n_checkpoints_to_keep`).
- Actions the GUI can offer: **resume** (new launch with `checkpoint_load_folder` = chosen checkpoint, same save folder
  → continues in the same run folder), **fork/fine-tune** (different run name / save folder; change lr etc.),
  **checkpoint now** (control command `c`), **export model** (`actor_critic.pt`), **protect from pruning** (copy out
  to a studio-managed folder; never mark inside the run folder).

## 7. Implications for our architecture (input for ADRs)
1. **Two-sided adapter.** The FastAPI backend should not import torch/rlgym (heavy, CUDA-specific, user-version-
   specific). Split `packages/rlgym-adapter` into: a *host side* (pure Python, used by the backend: paths, file
   formats, launching, parsing events) and a *runner side* (runs inside the user's training interpreter: imports the
   user entrypoint, injects config, overrides keyboard control, installs the studio metrics logger, emits JSON
   events, and offers an **introspection command** that dumps the JSON schema of the concrete config + available
   devices + library versions). Both talk via files/stdio/local socket only. → candidate **ADR-0004**.
2. **Interpreter management** per project: pick a Python executable/venv, check versions of rlgym-learn / algos /
   torch / CUDA via the introspection command, show actionable errors.
3. **Config schema = upstream schema + studio envelope.** Our persisted file wraps the upstream
   `LearningCoordinatorConfigModel` JSON verbatim plus studio metadata (`schemaVersion`, entrypoint, interpreter,
   upstream versions). Migrations apply to the envelope; upstream-shape changes are handled by the adapter per
   supported upstream version.
4. **Form generation from JSON schema** obtained by introspection, with hand-tuned UI hints for well-known models
   (PPO, GAE, wandb) and a generic fallback (raw JSON editor) for unknown user components.
5. Run folder layout owned by the studio, with the upstream checkpoint tree inside it (cwd = run folder).
6. Fake runner for tests: emits the same event stream and writes the same file layout without torch — lets QA and
   UI work run on CI machines without rlgym installed.

## 8. Candidate extension points (public API at 1.0)
- **Entrypoint contract**: a Python module exposing e.g. `build(ctx) -> (env_create_function, agent_controller)`
  (names TBD), where `ctx` gives the resolved config and run paths.
- **Metrics**: any `DictMetricsLogger` works; we document the `metrics.jsonl` format so third-party tools can read it.
- **Run event stream** (runner → backend): documented JSON events (started, heartbeat, iteration, checkpoint, paused,
  stopped, crashed, log line).
- **Control commands** (backend → runner): pause, resume, checkpoint, stop, add/remove process, set min-frac.
- **Templates**: starter entrypoints (e.g. the upstream quick-start Rocket League PPO setup) users can copy.
