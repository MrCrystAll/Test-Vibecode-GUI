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
