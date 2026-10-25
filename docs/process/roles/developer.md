# Developer playbook `[DEV-A]` / `[DEV-B]`

## Loop
1. **Reviews first.** If the other developer has a ticket in `To Review`, review it before starting new work.
2. Pick the top unblocked `To Do` ticket (see JQL in workflow.md). Prefer tickets that don't touch the files the other
   developer is working on. Assign yourself, move to **In Progress**, comment `[DEV-x] picked up`.
3. Create a worktree from up-to-date `dev`: `git worktree add ../wt-TC-<n> -b feat/TC-<n>-<slug> origin/dev`
   (or use the session's own worktree if it has one).
4. Implement with tests. Run lint + unit tests locally. Update docs/ADRs when you change architecture.
5. Push, open PR against `dev` (see workflow.md), wait for CI green, move ticket to **To Review**, comment with PR link,
   and message the other developer.
6. If you cannot proceed: follow the *Blocked* procedure in workflow.md, then move on to another ticket.

## Reviewing
- Move the ticket to **In Review**. Check: acceptance criteria met, tests meaningful, architecture rules in CLAUDE.md
  respected (no rlgym import outside the adapter, no app→app imports, contract regenerated), readable code.
- Approve → `gh pr review <n> --comment -b "[DEV-x] APPROVED ..."`, add label `reviewed`, squash-merge, tag the alpha
  pre-release (`v0.N.0-alpha.K`, push the tag), move the ticket to **In Test**, comment the tag.
- Changes needed → `[DEV-x] CHANGES REQUESTED` with concrete points, ticket back to **In Progress**, message the author.

## Rules
- One ticket = one branch = one PR. Never push directly to `dev` or `main`.
- Rebase/merge `dev` into your branch before requesting review if it's behind.
- Don't redesign product scope on your own — ask the PO in the ticket.
