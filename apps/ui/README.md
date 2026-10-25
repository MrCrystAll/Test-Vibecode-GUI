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
