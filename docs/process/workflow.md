# Team workflow

Four AI agents and a supervisor work this repo, coordinated through **Jira project `TC`**
(https://mathsuch63.atlassian.net, cloudId `7cf42fa5-f7fa-41ec-9758-6dd34429a227`) and git
(GitHub: https://github.com/MrCrystAll/Test-Vibecode-GUI, private; use `gh`).
All agents share one human's Jira/GitHub identity, so **every Jira comment, PR description and PR review starts
with a role tag**: `[PO]`, `[DEV-A]`, `[DEV-B]`, `[QA]`, `[SUPERVISOR]`.

| Role | Tag | Playbook |
|---|---|---|
| Product owner | `[PO]` | [roles/product-owner.md](roles/product-owner.md) |
| Developer A / B | `[DEV-A]` / `[DEV-B]` | [roles/developer.md](roles/developer.md) |
| Tester | `[QA]` | [roles/tester.md](roles/tester.md) |
| Supervisor | `[SUPERVISOR]` | [roles/supervisor.md](roles/supervisor.md) |

The human owner has the final say on product direction; the supervisor relays.

## Jira

### Issue hierarchy
- **Epic** = one minor version (e.g. `0.3.0`). Has a Jira *fix version* with the same name.
- **Story / Task / Bug** = one shippable increment under an epic → one alpha (or beta, for bugs) pre-release.
- Subtasks are optional, for a developer's own breakdown.

### Statuses
`To Do → In Progress → To Review → In Review → In Test → Done`

| Status | Meaning | Who moves it in |
|---|---|---|
| To Do | Ready and unblocked (PO guarantees acceptance criteria exist) | PO |
| In Progress | A developer owns it (assignee set, comment `[DEV-x] picked up`) | Developer |
| To Review | PR open against `dev`, CI green, PR link in a comment | Author developer |
| In Review | The *other* developer is actively reviewing | Reviewer |
| In Test | Merged into `dev`; waiting for / under QA | Reviewer after merging |
| Done | QA validated against the acceptance criteria | QA |

Rejected review (Jira transition *Review failed*) and failed QA (*Validation failed*) both send the ticket back to
**To Do**, keeping its assignee; the reviewer/QA comments why (QA also links a Bug when useful). A developer always picks
up **their own returned tickets first**, before new work (JQL: `status = "To Do" AND assignee = currentUser() AND comment ~ "FAILED OR CHANGES REQUESTED"`).

### Ownership and avoiding duplicate work
All agents share one Jira account, so the assignee field can't tell them apart. Instead:
- **Claim with a label.** Picking up a ticket = add `owner:dev-a`, `owner:dev-b`, `owner:qa` or `owner:po` (and the
  `[ROLE] picked up` comment). Never start a ticket that carries someone else's `owner:` label; ask them instead.
  Remove your label only when handing the ticket to someone else.
- **Search before you file or fix.** Before creating a Bug, or starting a fix for a failure you saw, search Jira
  (`project = TC AND statusCategory != Done AND text ~ "<key words>"`) **and** open PRs (`gh pr list --search "<words>"`).
  If it's already filed or being fixed, comment there instead.
- **A ticket with an open PR is never reassigned** or restarted by someone else; status alone isn't enough to tell, so
  check `gh pr list --search "TC-<n>"` first.
- **Duplicates and dropped tickets:** link `duplicates` to the original, add the label `duplicate`, comment, then close it
  with the Jira transition **Won't do / Duplicate** (available from To Do). The PO closes dropped tickets the same way.

### Blocked
A ticket that cannot move is **not** a status. Instead:
1. add label `blocked`, 2. add an issue link *"is blocked by"* to the blocking ticket (create one if none exists),
3. comment `[ROLE] BLOCKED: <reason / question>`.
The PO sweeps `labels = blocked` regularly, resolves or escalates, and removes the label when unblocked.
Developers never pick up `blocked` tickets.

**Dependency unblocking:** a ticket blocked only by other tickets becomes workable once **every** blocker is merged into
`dev` (status In Test or Done). Whoever merges a PR checks the tickets its ticket blocks; for each one whose blockers are
now all merged, they remove the `blocked` label, comment `[ROLE] unblocked: TC-x merged in <tag>`, and message the
developer/QA whose track it is. Blocks that need a decision (not a ticket) are only lifted by the PO.

### Useful JQL
- Next work for devs: `project = TC AND status = "To Do" AND (labels IS EMPTY OR labels != blocked) ORDER BY rank`
- Review queue: `project = TC AND status = "To Review"`
- QA queue: `project = TC AND status = "In Test"`
- Blocked: `project = TC AND labels = blocked`

## Git

**CI:** every PR runs `.github/workflows/ci.yml` on Windows and Linux. Run the same checks locally with
`uv run --no-project python tools/ci/run.py all` (details: [tools/ci/README.md](../../tools/ci/README.md)).

### Branches
- `main` — released versions only. Every commit on `main` is tagged `vX.Y.Z`.
- `dev` — integration branch. Every merged story is tagged as a pre-release.
- `feat/TC-<n>-<slug>`, `fix/TC-<n>-<slug>`, `chore/TC-<n>-<slug>` — one branch per ticket, branched from `dev`,
  each in its **own git worktree** (never switch branches inside a shared checkout).

### Commits
[Conventional Commits](https://www.conventionalcommits.org): `feat(ui): add run list (TC-12)`. Scopes: `desktop`, `ui`,
`backend`, `adapter`, `contract`, `config`, `ci`, `docs`. Breaking changes use `!` / `BREAKING CHANGE:` footers.

### Pull requests
- Target `dev`. Title = conventional-commit summary + ticket key. Body: ticket link, what/why, test evidence, screenshots for UI.
- Peer review is mandatory: DEV-A reviews DEV-B and vice-versa. Because both share one GitHub account, approval is a
  `gh pr review --comment` starting with `[DEV-x] APPROVED` plus the label `reviewed`. Change requests: `[DEV-x] CHANGES REQUESTED`.
- The approval comment names the reviewed commit: `[DEV-x] APPROVED at <short SHA>`. **The author pushes nothing to an
  approved PR**; a later push means a new review is needed (say so in the PR).
- Merge = **squash merge** by the reviewer once approved and CI is green, then tag (see below) and move the ticket to In Test.
  Always pin the approved commit so a late push can't slip in or get lost:
  `gh pr merge <n> --squash --match-head-commit <approved full SHA>`.
  **Who merges:** the agents' sessions are usually refused `gh pr merge` by Claude Code's safety check (every agent is
  the same GitHub account, so it looks like self-merging). So the reviewer, once the approval is posted, messages the
  **supervisor** with `PR #, approved SHA` (batch several in one message). The supervisor merges under the owner's
  standing authorization (2026-10-25) when the PR has: a `[DEV-x] APPROVED at <sha>` from an agent other than the
  author, the `reviewed` label, a head equal to that SHA, and green CI once CI exists. The check is done
  **immediately before merging** and uses the reviewer's **latest** verdict: their most recent review/comment must
  start with `[DEV-x] APPROVED at <current head SHA>`. Any later `CHANGES REQUESTED` (including one that withdraws an
  approval) voids it, and so does a later push. To withdraw an approval, a reviewer posts `[DEV-x] CHANGES REQUESTED`
  **and removes the `reviewed` label**, so the withdrawal is visible in two places. The supervisor then tags,
  moves the ticket to In Test, applies the unblocking rule and messages `qa`. A reviewer whose own merge does go
  through may finish those steps themselves.
- **ADRs:** the PR sets the ADR to `Status: Accepted (YYYY-MM-DD)` before approval; merging the PR *is* the acceptance.
  A rejected ADR is closed, not merged. Superseding happens in a new ADR.
- Release PRs `dev → main` are opened by the supervisor after QA signs off an epic, and merged with a merge commit.

## Versioning (SemVer 2.0 with pre-releases)
- Epic targeting `0.N.0` (later `X.Y.0`): each story merged into `dev` is tagged `v0.N.0-alpha.K` (K increments from 1).
- When every story of the epic is Done, QA tags `v0.N.0-beta.1`; fixes during stabilisation → `beta.2`, `beta.3` …
- QA sign-off → release PR to `main`, tagged `v0.N.0`, Jira fix version released.
- Hotfix on a release: `fix/` branch from `main`, patch bump `v0.N.1`, merged back into `dev`.
- **1.0.0 freezes the public API** (HTTP/WS contract, config schema, extension points). After that, breaking = major.
- Tag lookup before tagging: `git tag --list "v0.N.0-*" --sort=-v:refname | head -1`.

## Ticket comments: the work journal
The owner follows the team through Jira comments, so **write in the ticket while you work, not just at transitions**.
Always prefix with your role tag. Comment when you:
- pick up a ticket: your plan in 2–5 bullets (approach, files/areas touched);
- hit a struggle: `[ROLE] STRUGGLING: <what you tried, what failed, what you'll try next>`. Write it as soon as
  something costs more than one failed attempt (failing CI you can't explain, unclear upstream behaviour, tooling on
  Windows, ambiguous acceptance criteria), even if you solve it later. The owner and supervisor use these to improve
  the process;
- make a decision not covered by the ticket (and why), or deviate from the plan;
- hand over (To Review, In Test, Done, back to In Progress): what changed, how it was verified, PR/tag links;
- review or test: findings, linked from the PR review / Bug.
Keep comments factual and short. Questions for someone go in the ticket **and** a message to them.

## Agent-to-agent communication
- **Jira is the source of truth**; messages are for nudges and questions. Anything decided in a message gets written
  into the ticket as a comment.
- Agents are long-lived Claude sessions named `product-owner`, `dev-a`, `dev-b`, `qa`; the supervisor is the session
  that started them. Message each other with SendMessage (find names with ListAgents). A message wakes an idle agent,
  so **always message the next person in the chain** at a hand-over: author → other dev (To Review), reviewer → author
  (changes requested / merged), merger → `qa` (In Test) and any dev/QA whose ticket got unblocked, QA → author (Bug).
- **Keep working until there is nothing you can do**: after finishing a ticket, take the next one (reviews first). End
  your turn only when you have no unblocked work, with a short status report (what you did, what you're waiting on).
- Keep messages short and actionable.
- Escalation path: developer/QA → PO (product questions) → supervisor (process / cross-team) → human owner.
- **Upstream (rlgym-learn / rlgym-learn-algos):** never open issues or PRs upstream. If a limitation needs an upstream
  change, write it up in a Jira ticket labelled `upstream` and escalate to the supervisor; the owner handles it with
  the upstream author.
