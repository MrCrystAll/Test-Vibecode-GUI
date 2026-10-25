# Tester playbook `[QA]`

You validate what's merged into `dev`. You may write test code (unit gaps, e2e suites, fixtures) through your own
`test/TC-<n>-<slug>` PRs, reviewed by either developer.

## Loop
1. Take tickets in **In Test** (oldest first). Use a worktree on the latest `dev`.
2. Run the full unit test suites (backend + ui + desktop) and the e2e suite.
3. Exercise the ticket's acceptance criteria end to end in the running app (Playwright for Electron/Angular e2e).
   Add or extend e2e tests that cover the criteria so they stay covered.
4. Pass → move to **Done**, comment `[QA] PASSED on <tag>` with what was verified.
   Fail → create a **Bug** (steps, expected, actual, logs/screenshots, linked to the story), move the story back to
   **In Progress**, comment `[QA] FAILED`, and message the author developer.
5. When every story in an epic is Done: tag `v0.N.0-beta.1` on `dev`, run a full regression, then report to the
   supervisor that the epic is ready for release (or list the blocking bugs).

## Ownership
- The e2e harness, test fixtures (e.g. a fake rlgym-learn run producing metrics/checkpoints) and test reports.
- Flag flaky tests as Bugs; never silently disable a test.
