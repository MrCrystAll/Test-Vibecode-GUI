# Product vision

Owner: `[PO]`. Status: approved by the owner (2026-10-25).

## One-liner
A local desktop studio that makes training RL agents with **rlgym-learn** visible and repeatable: configure a run
in forms instead of editing Python, launch and control it with buttons instead of terminal keys, watch it live, and
find, compare and resume every past run from the files on your disk.

## Target users
1. **Hobbyist / community bot makers** (primary) — train agents for any RLGym v2 environment with rlgym-learn on
   their own PC (Windows or Linux, often one consumer GPU). Rocket League bots are the most common case today. Comfortable enough with Python to write rewards and obs builders, but tired of
   editing scripts for every hyper-parameter, losing track of runs, and juggling terminals and wandb.
2. **Experienced RL practitioners / researchers** — run many experiments, multi-agent setups (self-play, several PPO
   controllers), custom agent controllers. Need reproducibility, comparison, and a GUI that never hides the raw
   config.
3. **Third-party tool builders** — want to build dashboards, schedulers, bot-sharing tools or CI on top of a stable
   local API and documented file formats instead of scraping logs.

## Problems we solve
- **Config is buried in code.** Hyper-parameters live in a Python script or a hand-edited `config.json` whose shape
  depends on the chosen components; mistakes surface only when the run crashes at startup.
- **Control is keyboard-only.** Pause/checkpoint/quit/add process are single keys in the training terminal; there is no
  safe stop from anything else.
- **Monitoring is either stdout or a cloud service.** Metrics are printed per iteration or sent to wandb; there is no
  local, offline, live view.
- **Run tracking is folder archaeology.** Checkpoints are `<time_ns>` folders; which config produced which checkpoint,
  how far a run got and how to resume it are manual knowledge.
- **Debugging is guesswork.** Crashes in env processes, wrong interpreter, missing CUDA, bad serde types — all show up
  as long tracebacks in a terminal.

## Product principles
1. **Local first, local only.** Training runs as child processes on the user's machine, forever (ADR-0003). The app
   is fully usable offline; cloud services (wandb) are optional integrations, never requirements.
2. **Files are the truth.** Projects, configs and run metadata are human-readable files with a `schemaVersion` and
   migrations (ADR-0002). Users can diff, commit and share them. Anything else (indexes, caches) is rebuildable.
3. **Never hide rlgym-learn.** The studio wraps the upstream config verbatim, always offers the raw JSON next to the
   form, and runs the user's own Python code. A user can always leave the studio and run the same thing by hand.
4. **Upstream behind one adapter.** rlgym-learn evolves fast; changes are absorbed in one package with explicit
   supported-version ranges, not spread across the app. The API process never imports torch; anything that needs
   rlgym-learn or torch runs in the user's own training interpreter, through the adapter.
5. **Environment-agnostic core.** The studio works with any RLGym v2 environment. Rocket League support lives only in
   templates and examples.
6. **The API is the product.** Everything the UI does goes through the documented HTTP/WS contract, so third parties
   can do the same. From 1.0.0 it is semver-stable.
7. **Safe by default.** Never write inside upstream checkpoint folders, never load untrusted pickles silently, always
   try to stop gracefully with a checkpoint before killing.
8. **Boring and durable.** Explicit, modular, well-tested code; fewer features done well beats many done halfway.

## Non-goals (permanent)
- **Remote or distributed training** — no remote workers, clusters, cloud GPUs or job schedulers. Ever.
- **A database as source of truth** — persistence is the file system unless an ADR supersedes ADR-0002.
- **Replacing rlgym-learn** — we do not reimplement PPO, env processes or the RLGym API.
- **Managing the user's Python environment** — we detect and validate an interpreter; we do not install torch/CUDA
  or vendor rlgym-learn.
- **A general-purpose ML experiment tracker** — we track rlgym-learn runs, not arbitrary frameworks.
- **Hosting or multi-user collaboration** — single user, single machine; sharing happens through files and git.
- **Contributing upstream** — we never open issues or PRs on rlgym-learn / rlgym-learn-algos; the owner handles
  upstream relations.
- **macOS** — the supported platforms are Windows and Linux.

## Non-goals (for now, may be revisited after 1.0)
- Visual editors for reward functions / obs builders (code stays code).
- Embedded 3D match viewer (rlviser is launched as-is via `render`).
- Non-English UI (strings are externalised from day one, so translations can be added later).
- Hyper-parameter sweeps / automatic tuning.
- Plugin marketplace.

## Success measures
- A new user goes from installed app to a running quick-start training in **under 15 minutes** with an existing
  Python environment.
- Every run started from the studio can be **resumed or reproduced** from its folder alone.
- A third party can build a working read-only dashboard against the 1.0 API using only the published docs.
- Zero data-loss bugs: a user-initiated stop always produces a usable checkpoint.
