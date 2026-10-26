# Team runbook: starting and restarting the agents

Owned by the supervisor. How to bring the AI team up from nothing, e.g. after a machine change, a repo move or a long pause.
All team state lives in **Jira (TC)** and **GitHub**; sessions are disposable.

## Environment requirements
- Repo on an **NTFS** (or ReFS) volume. exFAT/FAT drives have no symlinks/junctions and break pnpm/Electron tooling.
- `gh` authenticated; Atlassian MCP connector enabled in the Claude Code app.
- `.claude/settings.json` (committed) allows `gh pr merge` for peer-approved PRs only (see workflow.md).
- Toolchain versions are pinned in the repo (see root README after TC-11).

## Sessions
| Name | Role | Worktree | Playbook | Model |
|---|---|---|---|---|
| `product-owner` | `[PO]` | own, from `dev` | roles/product-owner.md | Sonnet |
| `dev-a` | `[DEV-A]`, Track A (backend, adapter, config-schema) | own, from `dev` | roles/developer.md | Opus |
| `dev-b` | `[DEV-B]`, Track B (ui, desktop, generated client) | own, from `dev` | roles/developer.md | Opus |
| `qa` | `[QA]` | own, from `dev` | roles/tester.md | Sonnet |

Model choice is the owner's (2026-10-26): developers on the strongest model, PO and QA on Sonnet to save usage.
The supervisor session runs in the main checkout (on `dev`) and starts the others.

## Restart brief (template)
Give each session this brief, filled in:

> You are **<ROLE> `[TAG]`**, a long-lived member of the team. Read `CLAUDE.md`, `docs/process/workflow.md`,
> `docs/process/roles/<playbook>.md` and `docs/product/roadmap.md`. You are **resuming**, not starting: rebuild your state
> from Jira and GitHub before doing anything new:
> 1. JQL `project = TC AND comment ~ "[TAG]" AND status not in (Done)`, plus open PRs (`gh pr list`). Read the latest
>    `[TAG] CHECKPOINT:` comment on each ticket.
> 2. Fetch your branches from `origin` into fresh worktrees from `origin/dev`.
> 3. Continue the loop in your playbook (reviews first). Keep the Jira work journal.
> Peers: `product-owner`, `dev-a`, `dev-b`, `qa`; escalate process issues to the supervisor.

## Checkpoint before stopping the team
The supervisor messages every agent: push all branches (`wip:` commits allowed), comment `[TAG] CHECKPOINT: <state, next
step, branch, PR>` on each owned ticket, start nothing new, and end the turn. Only then stop or archive the sessions.
