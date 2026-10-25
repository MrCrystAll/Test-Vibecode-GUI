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
