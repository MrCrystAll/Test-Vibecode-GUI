# Licensing policy

The project is licensed under the **Apache License 2.0** (owner decision). The root [LICENSE](../../LICENSE) holds the
unmodified licence text and [NOTICE](../../NOTICE) the attribution notice. Keep both files at the repository root and
never edit `LICENSE`.

## Headers in source files
Every **hand-written** source file starts with a single SPDX line in the file's comment syntax, and nothing else
(no copyright block, no full licence text):

```ts
// SPDX-License-Identifier: Apache-2.0
```
```python
# SPDX-License-Identifier: Apache-2.0
```

- Applies to: `.ts`, `.js`, `.mjs`, `.cjs`, `.py`, `.scss`/`.css`, `.html` templates (as `<!-- ... -->`), shell and
  PowerShell scripts.
- Not required in: generated files (e.g. `packages/contract/src/generated/`, `openapi.json`), JSON/YAML/TOML config,
  Markdown, lock files, test fixtures and data files. Generated files must not be edited to add a header, as that would
  break the contract drift check (ADR-0006).
- Copyright lives in `NOTICE` only, so the header never needs a year bump.
- A lint check for missing headers may be added with the CI licence stories (TC-26/TC-28); until then reviewers check it.

## Third-party code
- **`.reference/` is read-only study material.** Upstream code there (rlgym-learn, rlgym-learn-algos, …) is never
  copied, pasted or vendored into this repository, in whole or in part, so its licence is not mixed with ours.
  We depend on upstream only as installed packages through the adapter (CLAUDE.md rule 3).
- Dependencies must use licences compatible with Apache-2.0, checked in CI (see below).
- If code from another project is ever included verbatim (with owner approval), keep its original licence header, add
  its licence file next to it, and add its required attribution to `NOTICE`.

## Dependency licences (TC-28)
Every npm and Python dependency, transitive and dev-only included, is checked on each CI run by
[`tools/ci/hooks/licenses.py`](../../tools/ci/hooks/licenses.py) against
[`tools/ci/licenses.toml`](../../tools/ci/licenses.toml). Python licences come from the locked workspace environment
(`License-Expression`, else the `License` field, else trove classifiers); npm licences from
`pnpm -r licenses list --json`. SPDX expressions are evaluated: `A OR B` needs one allowed side, `A AND B` both.

**Allowed:** `0BSD`, `Apache-2.0`, `BlueOak-1.0.0`, `BSD-2-Clause`, `BSD-3-Clause`, `CC0-1.0`, `ISC`, `MIT`, `MIT-0`,
`MPL-2.0`, `PSF-2.0`, `Python-2.0`, `Unlicense`, `Zlib`. All are permissive except MPL-2.0, which is file-level
copyleft: using an unmodified MPL package is fine; a modified MPL file must stay MPL and be published. Anything else
(GPL/LGPL/AGPL, SSPL, unknown or missing licence, …) fails the job with the package name.

**Exceptions** are `[[exception]]` entries in `licenses.toml` with the ecosystem, package, the exact licence and a
`reason` (plus a comment explaining it). An exception never covers another package or a changed licence, and the
check warns when one no longer matches anything. Current exception: `caniuse-lite` (CC-BY-4.0), build-time browser
data; attribution goes in the notices file.

**Changing the policy** (a new licence or exception) is a PR reviewed by the other developer; new copyleft licences need
the owner's approval through the PO.

**Third-party notices** for the future installer:
`uv run --locked --all-packages python tools/ci/hooks/licenses.py --notices THIRD_PARTY_NOTICES.md` (name, version,
licence, homepage and the licence texts found in each package). Not committed yet.
