# v0.N.0-beta.K — QA sign-off report

<!-- Copy to docs/qa/reports/v0.N.0-beta.K.md, fill in, commit through a test/ PR. See test-strategy.md §10. -->

- Epic: TC-x (`0.N.0`) · Test plan: [docs/qa/0.N.0-test-plan.md](../0.N.0-test-plan.md)
- Tag: `v0.N.0-beta.K` → commit `<sha>` · Previous beta: `<tag or none>`
- Tested by `[QA]` on `<date>`
- Environments: Windows `<edition, build>` (`<machine/VM>`) · Linux `<distro, version>` (`<machine/VM/WSL2>`)
- Toolchain: Node `<v>`, pnpm `<v>`, Python `<v>`, uv `<v>`

## 1. Scope check
- [ ] Every story/task of the epic is **Done** in Jira (list keys)
- [ ] No open Bug with fix version `0.N.0` at Blocker / Critical; every open Major has a written PO deferral
- [ ] Test plan up to date: every AC and exit criterion has a test case

## 2. Automated suites (CI run on the tag: `<run link>`)
| Suite | Windows | Linux | Notes |
|---|---|---|---|
| Static checks (lint, types, boundaries, drift, licences) | ☐ | ☐ | |
| Unit — backend | ☐ | ☐ | |
| Unit — adapter / config-schema | ☐ | ☐ | |
| Unit — UI | ☐ | ☐ | |
| Unit — desktop | ☐ | ☐ | |
| API (`tests/api`) | ☐ | ☐ | |
| E2E (`tests/e2e`, all epics) | ☐ | ☐ | flaky (pass-on-retry): `<list or none>` |

- Quarantined tests (with Bug keys): `<list or none>` — none may cover an exit criterion of this epic.

## 3. Exit criteria
| ID | Criterion | Windows | Linux | Evidence |
|---|---|---|---|---|
| X-1 | | ☐ | ☐ | |

## 4. Manual test cases
| ID | Windows | Linux | Notes / Bug |
|---|---|---|---|
| T-…/M-… | ☐ | ☐ | |

Regression manual cases from earlier epics: `<list>` ☐

## 5. Exploratory session
- Charter, duration per OS, findings (with Bug keys).

## 6. Compatibility (0.2.0+)
- [ ] Migration corpus loads; previous release's workspace opens and keeps a backup
- [ ] Upgrade from the previous release's build (1.0.0+: auto-update path)

## 7. Since the previous beta (beta.2+)
- Fixes included (Bug keys + PRs), what was rerun (full automated + areas + smoke).

## 8. Verdict
- [ ] **SIGNED OFF** — ready for the release PR `dev → main` as `v0.N.0`
- [ ] **NOT READY** — blocking Bugs: `<keys>`; next step: `<…>`
