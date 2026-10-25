# tests/fixtures — shared black-box test data

Owner: `[QA]`. Rules: [test strategy §5](../../docs/process/test-strategy.md). Short version: fixtures are
**read-only inputs**. A test copies one into its own temp dir (`tests/api/harness/paths.py`:
`workspace_from_fixture`, `copy_fixture`; the e2e harness has the same helpers) and never writes here.

Generated fixtures are produced by a committed script and must not be edited by hand. After changing the script,
regenerate and commit; `--check` fails when the committed files are stale:

```bash
uv run --no-project python tests/fixtures/workspaces/generate.py
uv run --no-project python tests/fixtures/workspaces/generate.py --check
```

## Index

| Path | What | Format version | Made by | Used by |
|---|---|---|---|---|
| `workspaces/empty/` | Initialised workspace (`.studio/workspace.json`), no projects | workspace v1 | `workspaces/generate.py` | T-34-4, T-39-2 |
| `workspaces/one-project/` | One valid project `first-project` | project v1 | `generate.py` | T-34-4, M-TWO, M-KILL |
| `workspaces/many-projects/` | 250 valid projects `project-001..250`: every 10th archived, every 7th has a non-ASCII name, every 11th a 100-char name, every 3rd a description, every 50th an unknown key `userNote`; `updatedAt` order differs from id order | project v1 | `generate.py` | X2-3, T-37-2, T-39-1, M-CACHE |
| `workspaces/broken/` | `valid-project` next to `invalid-json`, `missing-name`, `wrong-type`, `too-new` (schemaVersion 999), `empty-file`, `not-an-object` | project v1 (+ v999) | `generate.py` | X2-4, T-32-5, T-36-3, T-39-3 |
| `workspaces/external-edit/` | `edit-me` + `bystander`: start state for hand edits | project v1 | `generate.py` | T-36-4, T-37-3, M-ED |
| `workspaces/not-a-workspace/` | Non-empty folder without `.studio/` (opening it must give `workspace_not_empty` and write nothing) | — | `generate.py` | T-34-4, T-38-3 |
| `edits/project-json/` | Replacement files for `external-edit/edit-me/project.json`: `renamed`, `extra-key`, `too-new`, `invalid-json`, `crlf-bom` (UTF-8 BOM + CRLF, kept byte-exact by `.gitattributes`) | project v1 | `generate.py` | T-32-2, T-36-4, M-ED |

Not committed on purpose:
- `.studio/lock`, `.studio/cache/` and `.studio/trash/`: created by the backend at runtime. Git cannot hold empty
  folders, and a committed lock or cache would test a state the app never produces. Tests that need a corrupt
  cache write it into their temp copy.
- Uninitialised empty folders: a test creates one with `hostile_tmp`.
- Windows reserved names (`con/`, `nul/`): they cannot exist on Windows checkouts. Covered through the API
  (`invalid_project_id`).

## Relation to the migration corpus (TC-33, agreed in TC-42)
`packages/config-schema/tests/fixtures/<kind>/v<N>/` is the **only** home of per-file historical samples. It is
owned by developers, append-only, and loaded by the package's unit tests. QA does not keep a copy here. Black-box
tests that need an old-version file (X2-2, once a real v2 exists) read the corpus file as data, like the contract
artefacts in `packages/contract/` (strategy §3), and copy it into their temp workspace. Workspace fixtures here
are whole-workspace scenarios at the **current** version only. When a format version is bumped, the developer adds
the old sample to the corpus (TC-33 README), and QA updates `generate.py` and regenerates.
