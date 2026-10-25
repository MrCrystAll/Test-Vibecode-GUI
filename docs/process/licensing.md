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
- Dependencies must use licences compatible with Apache-2.0. The CI check for this is TC-28.
- If code from another project is ever included verbatim (with owner approval), keep its original licence header, add
  its licence file next to it, and add its required attribution to `NOTICE`.
