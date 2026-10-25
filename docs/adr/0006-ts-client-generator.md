# ADR-0006: TypeScript client generated from OpenAPI

- Status: Proposed (2026-10-25)
- Ticket: TC-13

## Context
The backend's OpenAPI schema is the source of truth for the API (CLAUDE.md rule 2), and the Angular UI must talk to the
backend only through a client generated from it. The client lives for years, so it must be boring to maintain. It is
frozen as part of the public API at 1.0.0. Requirements from the ticket:

1. strict TypeScript output (`strict: true`, no `any` leaking into UI code);
2. fits Angular standalone components with signals and RxJS;
3. typed WebSocket messages, not only HTTP;
4. generation runs offline in CI on Windows and Linux;
5. healthy maintenance;
6. licence compatible with Apache-2.0.

Other constraints: the backend binds `127.0.0.1` on an ephemeral port and requires a per-launch bearer token on HTTP and
WebSocket (roadmap 0.1.0 A4, TC-19). Electron learns the port and token from the backend's stdout handshake (TC-23).

## Options considered

| | A. openapi-generator `typescript-angular` | B. `@hey-api/openapi-ts` (+ Angular client) | C. orval (Angular mode) | D. `openapi-typescript` + `openapi-fetch` |
|---|---|---|---|---|
| Output | One `@Injectable` service per tag, model classes, `HttpClient` | SDK functions + types; Angular `HttpClient` client plugin | Injectable services + types on `HttpClient` | One `.d.ts` of types (`paths`, `components`); generic typed `fetch` client, no per-endpoint code |
| Strict TS | Good, but nullable/oneOf handling is weak and has many config flags | Good | Good | Very good: types mirror the schema 1:1, including `oneOf`/discriminators |
| Angular fit | Native (`HttpClient`, interceptors), but emits NgModule-era boilerplate and `Configuration` objects | Native (`HttpClient`) | Native (`HttpClient`), also signals helpers | Framework-agnostic `Promise`s; wrapped once in an Angular service; `from()` for RxJS, `resource()` for signals |
| WebSocket types | Only via schemas in `components` | Only via schemas in `components` | Only via schemas in `components` | Only via schemas in `components` |
| Offline, Windows + Linux | Needs a **Java runtime** in CI and on dev machines (or Docker) | Node only | Node only | Node only |
| Maintenance | Very active, huge surface; generated code style changes between minors | Very active but **pre-1.0, frequent breaking changes** in config and output | Active, medium-sized project | Mature, stable (v7), small surface; same maintainers ship both packages |
| Licence | Apache-2.0 | MIT | MIT | MIT (both) |
| Generated code size | Large | Medium | Medium | Small (types only; runtime client ~6 kB) |

Hand-writing the client was rejected outright: it breaks rule 2 (the schema would not be the source of truth).

## Decision
**Option D: `openapi-typescript` generates types, `openapi-fetch` is the runtime client.** It has the least generated
code to review, no Java, the most faithful types, and the smallest upstream surface to track over many years. The cost
(no `HttpClient`, so no Angular interceptors or `HttpTestingController`) is paid once in a thin wrapper, see below.
Both packages are pinned to **exact** versions in `packages/contract/package.json`; upgrades are their own PR with the
regenerated diff.

### Where things live
```
packages/contract/
  openapi.json            # exported from the backend (TC-18), committed
  src/generated/schema.ts # openapi-typescript output, committed, never edited by hand
  src/client.ts           # createApiClient(): openapi-fetch client + auth middleware (hand-written, small)
  src/ws.ts               # typed WebSocket envelope helpers built on the generated types (hand-written, small)
  src/index.ts            # public entry: re-exports types, createApiClient, ws helpers
  package.json            # name e.g. "@studio/contract"; script "generate"
```
`packages/contract` does not import Angular or anything from `apps/*` (rule 1), so it stays reusable by the Electron
shell, e2e tests and third-party tools. Angular-specific wiring (injection tokens, providers, signal helpers) lives in
`apps/ui/src/app/core/api/`.

### Generated code is committed
- Reviewers see API changes as a diff in the PR that causes them.
- The UI and Electron build without a Python toolchain.
- Generated files are marked `linguist-generated` and forced to `eol=lf` in `.gitattributes`, so Windows checkouts do
  not produce CRLF drift.

### Drift check (fails CI)
Run on Windows and Linux in the CI pipeline (TC-26):
1. Backend step (TC-18): export the OpenAPI schema from the code into `packages/contract/openapi.json`.
2. Contract step: `pnpm --filter @studio/contract generate` (runs `openapi-typescript openapi.json -o src/generated/schema.ts`).
3. `git diff --exit-code -- packages/contract` → any difference fails the job with a message telling the author to run
   the generate script and commit the result.
4. `tsc --noEmit` over `apps/ui` and `apps/desktop`, so a breaking schema change that the UI does not handle also fails.

Generation must be deterministic: no timestamps or version banners in the output, schema keys emitted in a stable order
by the backend export.

### WebSocket message types
OpenAPI has no WebSocket support. The backend therefore **adds every WS envelope and event payload model to
`components.schemas`** of the exported `openapi.json` (a small hook around FastAPI's `openapi()`, owned by Track A in
TC-18/TC-20). The envelope is a discriminated union on `type`, so `openapi-typescript` emits a union the UI can
`switch` on. This keeps one schema file, one generator and one drift check. `src/ws.ts` adds only runtime helpers
(open, parse with a `version` check, typed `on(type, handler)`), no hand-written types.

### Per-launch auth token
- Electron's main process reads `{port, token}` from the backend handshake and holds them in memory only.
- The preload script exposes one function through `contextBridge`:
  `studio.getBackendConnection(): Promise<{ baseUrl: string; wsUrl: string; token: string }>` (IPC `invoke`).
  No Node APIs are exposed to the renderer.
- The UI calls it once at start-up (`provideAppInitializer`), then creates the single client instance with
  `createApiClient({ baseUrl, getToken })` and provides it through an `InjectionToken`. Components never see the token.
- HTTP: an `openapi-fetch` middleware sets `Authorization: Bearer <token>` on every request.
- WebSocket: browsers cannot set headers on `new WebSocket()`. The token is sent as a subprotocol:
  `new WebSocket(wsUrl, ["studio.v1", "bearer." + token])`; the backend validates it and echoes `studio.v1`.
  The token never appears in a URL, in storage (`localStorage`, cookies) or in logs. This needs Track A agreement in
  TC-19/TC-20.
- Token restarts: when the backend restarts (TC-24), Electron gets a new token; the UI re-runs the initializer path
  (`getBackendConnection()` again) instead of caching the token.
- Browser-only development (`ng serve` without Electron) uses a dev implementation of the same connection provider; its
  details belong to TC-22/TC-23.

### Angular usage
- `apps/ui/src/app/core/api/` provides the `ApiClient` token and thin per-feature services that call it and return
  signals (via `resource()`) or `Observable`s (via `from()`), whichever the feature needs.
- Unit tests pass a fake `fetch` to `createApiClient` (supported by `openapi-fetch`) instead of `HttpTestingController`.
- Error bodies are typed from the schema's error responses; the UI maps them to i18n message keys, never shows raw text
  as UI copy.

## Consequences
- One small runtime dependency and one dev dependency, both MIT, both pinned; no Java anywhere in the toolchain.
- Angular `HttpClient` features (interceptors, `HttpTestingController`, `httpResource`) are not used; cross-cutting
  behaviour (auth, error mapping, logging) goes into `openapi-fetch` middleware instead.
- The backend owns an extra hook to publish WS models in the OpenAPI document; forgetting a model there means the UI
  cannot type that event, which code review and the drift check surface.
- Because the generated types are part of the contract, a breaking schema change is visible in `schema.ts` diffs, which
  supports the 1.0.0 semver freeze.
- If `openapi-fetch` were abandoned, the generated types stay valid and the wrapper in `src/client.ts` is the only code to
  replace.
