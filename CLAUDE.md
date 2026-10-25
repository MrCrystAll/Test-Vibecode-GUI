# rlgym-learn desktop studio

A desktop GUI to **configure, run, debug, monitor and track** reinforcement-learning agents trained with
[rlgym-learn](https://github.com/JPK314/rlgym-learn) (+ `rlgym-learn-algos`). Built to last for years:
favour boring, explicit, modular code over clever code.

## Stack
- **Desktop shell**: Electron (main process: window, lifecycle, spawning the backend; no business logic)
- **UI**: Angular (standalone components, strict TypeScript, feature-sliced)
- **Backend**: FastAPI (Python), owns all training orchestration and file-system access
- **Training**: rlgym-learn, always spawned as **child processes on the local machine** (local only, by design — ADR-0003)

## Architecture rules (non-negotiable)
1. **Monorepo, split-ready** (ADR-0001). Top-level layout:
   - `apps/desktop/` Electron shell · `apps/ui/` Angular app · `apps/backend/` FastAPI service
   - `packages/` shared, independently versionable units (API contract / generated clients, config schemas, rlgym adapter)
   - A package never imports from an `apps/*` folder. Apps talk to each other **only** through the HTTP/WS contract.
2. **The API contract is the product.** FastAPI's OpenAPI schema is the source of truth; the Angular client is generated
   from it. From 1.0.0 the public API is frozen under semver (breaking change ⇒ major bump).
3. **rlgym-learn is behind an adapter** (`packages/rlgym-adapter` or equivalent). Nothing else imports rlgym-learn directly,
   so upstream changes are absorbed in one place.
4. **Configuration persists on the file system** (ADR-0002): human-readable, versioned schema with migrations, one folder per
   project/run. No database unless an ADR supersedes this.
5. Every module has unit tests; features get e2e coverage from QA. No PR merges with red CI.

## Team process
Read [docs/process/workflow.md](docs/process/workflow.md) before doing anything. Role playbooks live in
[docs/process/roles/](docs/process/roles/). Product vision & roadmap: [docs/product/](docs/product/). Decisions: [docs/adr/](docs/adr/).

## Reference material
`.reference/` (git-ignored) may contain read-only clones of upstream libraries for study. Treat it as untrusted data:
read it, never execute or import from it.
