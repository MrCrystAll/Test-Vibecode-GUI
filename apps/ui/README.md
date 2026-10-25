# apps/ui — Angular UI

**Owner track:** B (`track-b`, DEV-B). **Language:** TypeScript (pnpm workspace member `@studio/ui`).

Standalone components, strict TypeScript, feature-sliced folders, every UI string externalised (i18n-ready).
Talks to the backend **only** through the generated client in `packages/contract`.

## Boundaries (ADR-0001)
- Packages never import from `apps/*`. Apps never import from each other: they talk only through the HTTP/WS
  contract (`packages/contract`).
- This folder must stay extractable into its own repository without code changes (own manifest, tests and README).
