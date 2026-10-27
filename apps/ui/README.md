# apps/ui — Angular UI

**Owner track:** B (`track-b`, DEV-B). **Language:** TypeScript (pnpm workspace member `@studio/ui`).

Standalone components, strict TypeScript, feature-sliced folders, every UI string externalised (i18n-ready).
Talks to the backend **only** through the generated client in `packages/contract`.

## Boundaries (ADR-0001)
- Packages never import from `apps/*`. Apps never import from each other: they talk only through the HTTP/WS
  contract (`packages/contract`).
- This folder must stay extractable into its own repository without code changes (own manifest, tests and README).

## Commands
Run from `apps/ui/` (or `pnpm --filter @studio/ui <script>` from the repo root):

| Script | What it does |
|---|---|
| `pnpm start` | dev server on http://localhost:4200 |
| `pnpm lint` | angular-eslint (incl. the i18n rule) + `tools/i18n-lint.test.cjs`, which proves the rule rejects hard-coded text |
| `pnpm typecheck` | `ngc` on the app (strict templates) + `tsc` on the specs |
| `pnpm test` | unit tests, single run |
| `pnpm build` | production build into `dist/ui` |
| `pnpm extract-i18n` | extracts the message catalogue (`messages.xlf`) |

## Talking to the backend (TC-22)
Only through the generated client in `@studio/contract` (ADR-0006). `core/api/BackendApi` holds the single client
instance; `core/startup/Startup` connects it at start-up (after the desktop shell reports the backend ready). Components read `inject(BackendApi).client()` and never see
the token. ESLint rejects `fetch`, `XMLHttpRequest`, `WebSocket` and `@angular/common/http` everywhere in `src/`
(`tools/http-lint.test.cjs` proves it). The one exception is `core/api/backend-connection.ts`, which reads the dev
config below.

The connection (`baseUrl` + token) is learned at runtime, never hard-coded:
- **In Electron** (TC-23): from the preload bridge `window.studio.getBackendConnection()`.
- **In a plain browser** (`pnpm start`): from `public/dev-connection.json`, which is git-ignored. Set it up once:
  ```bash
  cp public/dev-connection.example.json public/dev-connection.json   # baseUrl "" = same origin, via the proxy
  uv run --package studio-backend studio-backend --port 8765          # from the repo root, in another shell
  pnpm start                                                         # proxy.conf.json forwards /api to :8765
  ```
  Once the backend requires a token (TC-19), paste the one from its handshake line into `token`.

Without a connection the app still starts; the System status screen (`/status`) then shows *Unreachable*.

Two dev-server details, because `@studio/contract` ships TypeScript source (no build step):
- `angular.json` → `serve.options.prebundle.exclude: ["@studio/contract"]`: Vite's dependency pre-bundler cannot
  resolve the package's extensionless `.ts` imports, so Angular compiles it like app code instead.
- `openapi-fetch` is also a direct dependency of this app, at the **same exact version** as in `packages/contract`
  (pnpm keeps one copy). The dev server resolves bare imports from `apps/ui`, and pnpm's strict layout otherwise
  hides the contract's own dependency. Bump both together.

## Folder structure (feature-sliced)
```
src/
  styles.scss, styles/_tokens.scss   global styles; theme tokens as CSS variables
  app/
    app.ts, app.config.ts, app.routes.ts   root component, providers, top-level routes
    core/        app-wide singletons and the layout (core/layout/shell: header + main area)
    shared/      reusable presentational components, directives, pipes (no feature logic)
    features/<feature>/   one folder per feature, lazy-loaded from app.routes.ts
```
Rules: a feature may import from `core/` and `shared/`, never from another feature. `shared/` imports nothing from
`core/` or `features/`. Unit tests (`*.spec.ts`) sit next to the file they test.

## Decisions
- **Angular 22, standalone, zoneless, OnPush.** `strict` TypeScript and `strictTemplates` are on (`tsconfig.json`).
- **i18n: Angular's built-in `@angular/localize`**, not Transloco. Templates mark text with `i18n` / `i18n-<attr>`, code
  uses `$localize`. English (`en-US`) is the source and only locale for 1.0. Chosen because angular-eslint's
  `template/i18n` rule fails lint on any hard-coded user-visible text or attribute, which enforces the rule mechanically.
  Message ids are explicit (`@@feature.key`) so translations survive copy edits.
- **Dates and numbers** always go through locale-aware pipes (`date`, `number`, `percent`, ...), plurals through ICU.
- **Unit tests: Vitest** (the Angular CLI default runner, `@angular/build:unit-test`) with jsdom.
- **Theming:** light/dark tokens in `styles/_tokens.scss`. Dark follows `prefers-color-scheme` unless
  `<html data-theme>` forces one. Components use the variables only, never raw colours.
- **Backend:** none yet. From TC-22 the UI talks to the backend only through the generated client in `packages/contract`.

## Windows on exFAT
Prefer an NTFS checkout. If you must use exFAT, `pnpm run` re-checks dependencies and reinstalls with symlinks, so the
root README's CLI flags are not enough: delete `node_modules`, then set these for **every** pnpm command:
`pnpm_config_node_linker=hoisted pnpm_config_hoist=false pnpm_config_package_import_method=copy pnpm_config_verify_deps_before_run=false`.
