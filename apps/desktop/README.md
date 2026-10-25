# apps/desktop — Electron shell

**Owner track:** B (`track-b`, DEV-B). **Language:** TypeScript (pnpm workspace member `@studio/desktop`).

Main process only: window, lifecycle, single-instance lock, spawning and supervising the backend (port + token
handshake on its stdout). No business logic here.

## Boundaries (ADR-0001)
- Packages never import from `apps/*`. Apps never import from each other: they talk only through the HTTP/WS
  contract (`packages/contract`).
- This folder must stay extractable into its own repository without code changes (own manifest, tests and README).
