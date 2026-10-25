# packages/rlgym-adapter — the only bridge to rlgym-learn

**Owner track:** A (`track-a`, DEV-A). **Language:** Python (uv workspace member `studio-rlgym-adapter`).

Two sides (design in ADR-0004):
- **host side** — pure Python, used by the backend: paths, file formats, launching runs, parsing runner events.
  Never imports torch, rlgym or rlgym-learn.
- **runner side** — runs inside the *user's* training interpreter (Python >= 3.10): loads the user's entrypoint,
  injects the config, controls the run, emits events, introspects versions/devices/config schema.

## Boundaries (ADR-0001)
- Packages never import from `apps/*`. Apps never import from each other: they talk only through the HTTP/WS
  contract (`packages/contract`).
- This folder must stay extractable into its own repository without code changes (own manifest, tests and README).
- **Nothing outside this package imports rlgym-learn**, and only the runner side may import torch, rlgym or
  rlgym-learn. Upstream changes are absorbed here, in one place.
- rlgym-learn, rlgym-learn-algos and torch are never declared as dependencies: they live in the user's interpreter.
  Supported upstream versions: rlgym-learn 2.0.x, rlgym-learn-algos 0.4.x.
