# packages/contract — API contract

**Owner track:** shared seam. The committed `openapi.json` is produced by Track A (exported from the backend); the
generated TypeScript client is owned by Track B. **Language:** TypeScript (pnpm workspace member `@studio/contract`).

The API contract is the product: from 1.0.0 it is frozen under semver. CI fails when `openapi.json` drifts from the
backend code.

## Boundaries (ADR-0001)
- Packages never import from `apps/*`. Apps never import from each other: they talk only through the HTTP/WS
  contract (`packages/contract`).
- This folder must stay extractable into its own repository without code changes (own manifest, tests and README).
- Contains only the schema and generated code: no hand-written business logic.

## Contents
| File | Produced by | Edit by hand? |
|---|---|---|
| `openapi.json` | the backend's `export-openapi` script (TC-18) | never |
| `src/generated/` | `openapi-typescript` (TC-22, ADR-0006) | never |

`openapi.json` is deterministic (UTF-8, LF, sorted keys, 2-space indent, trailing newline) and its `info.version`
is the contract version (`API_VERSION` in `apps/backend/src/studio_backend/version.py`), not the app version.
The `version` in `package.json` is this package's own version; it is aligned with the contract version when the
package is first published (1.0.0).

## Workflow: change a route → export → commit
1. Change or add a route in `apps/backend`. Give every operation an `operation_id` (it becomes the client method
   name), a router tag and a pydantic response model; errors are documented by the shared `ErrorResponse`.
2. From the repository root, regenerate the schema:
   ```bash
   uv run --package studio-backend export-openapi
   ```
3. Review the `openapi.json` diff (it *is* the API change) and commit it in the same PR as the route change. If the
   change is not backwards compatible, bump `API_VERSION` (ADR-0006, CLAUDE.md rule 2).

CI runs `export-openapi --check` (`tools/ci/hooks/contract-drift.py`) on Windows and Linux and fails with that
command in the message when the committed file differs from the code. The backend's `tests/test_openapi.py` runs
the same check, so `pytest` catches it locally too.
