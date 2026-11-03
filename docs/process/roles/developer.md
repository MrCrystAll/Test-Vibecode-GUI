# Developer playbook `[DEV-A]` / `[DEV-B]`

## Loop
1. **Reviews first, then your own returned tickets.** Review the other developer's `To Review` tickets, then fix any
   ticket of yours sent back to `To Do` by a failed review or QA, before starting new work.
2. Pick the top unblocked `To Do` ticket (see JQL in workflow.md). Prefer tickets that don't touch the files the other
   developer is working on. Assign yourself, move to **In Progress**, comment `[DEV-x] picked up`.
3. Create a worktree from up-to-date `dev`: `git worktree add ../wt-TC-<n> -b feat/TC-<n>-<slug> origin/dev`
   (or use the session's own worktree if it has one).
4. Implement with tests. Run lint + unit tests locally. Update docs/ADRs when you change architecture.
5. Push and open the PR against `dev` as your app (see *GitHub identity* below and workflow.md), wait for CI green, move ticket to **To Review**, comment with PR link,
   and message the other developer.
6. If you cannot proceed: follow the *Blocked* procedure in workflow.md, then move on to another ticket.

## Reviewing
- Move the ticket to **In Review**. Check: acceptance criteria met, tests meaningful, architecture rules in CLAUDE.md
  respected (no rlgym import outside the adapter, no app→app imports, contract regenerated), readable code.
- Approve → `uv run --script tools/agent/as_app.py dev-x -- gh pr review <n> --approve --body "[DEV-x] APPROVED at
  <short SHA> ..."`, add label `reviewed` (same wrapper), then send the supervisor `PR #, approved full SHA`. The
  supervisor merges (`--squash --match-head-commit <SHA>`), tags the alpha and moves the ticket to **In Test**.
- Changes needed → `as_app.py dev-x -- gh pr review <n> --request-changes --body "[DEV-x] CHANGES REQUESTED ..."` with
  concrete points, ticket back to **To Do** (*Review failed*), message the author.

## GitHub identity
Every GitHub write you make goes through your own app: `uv run --script tools/agent/as_app.py dev-a|dev-b -- <command>`
for `git commit`, `git push`, `gh pr create`, `gh pr review`, `gh pr edit`, `gh pr comment`. Commits then carry your bot
as author, and reviews count as real approvals. Never print, copy or commit the private keys in `%USERPROFILE%\.studio-agents\`.

## Rules
- One ticket = one branch = one PR. Never push directly to `dev` or `main`.
- Rebase/merge `dev` into your branch before requesting review if it's behind.
- Don't redesign product scope on your own — ask the PO in the ticket.
