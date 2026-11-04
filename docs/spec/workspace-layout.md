# Workspace layout

**Status:** draft during 0.x; **public from 1.0**. From 1.0.0 the paths, file kinds and rules below are part of
the frozen public API (semver: a breaking change means a major version). Story: TC-34. Decisions: ADR-0002 (files,
not a database), PO answers on TC-42 (Q3) and TC-2 (GO, 2026-11-03).

A **workspace** is a folder the user picks. It holds their projects, one folder each, as plain files they can read,
back up, put under version control and edit by hand.

## Tree

```
<workspace>/
  .studio/                    the studio's own folder (dot-folder: hidden on Linux, never a project)
    workspace.json            workspace marker: makes the folder a workspace
    lock                      workspace lock (OS lock while a backend has the workspace open)
    trash/                    deleted projects: <project-id>.<UTC timestamp>/
    cache/                    rebuildable data (index, ...): safe to delete at any time
  <project-id>/               one folder per project; its name is the project id
    project.json              the project file
    runs/                     reserved for training runs (0.4.0); do not use
  ...                         anything else is left alone (see "Other files")
```

| Path | Kind / content | Written by | Hand-editable |
|---|---|---|---|
| `.studio/workspace.json` | `kind: "workspace"` envelope ([schema](../../packages/config-schema/schemas/workspace.v1.schema.json)) | studio, at initialisation | no need; keep it |
| `.studio/lock` | OS lock; the text inside (`pid …`) is informational only | studio | no |
| `.studio/trash/` | folders of deleted projects, moved there whole | studio | yes: restore by moving a folder back, or delete it |
| `.studio/cache/` | rebuildable data | studio | delete only; it is rebuilt |
| `<project-id>/project.json` | `kind: "project"` envelope ([schema](../../packages/config-schema/schemas/project.v1.schema.json)) | studio and the user | **yes** |
| `<project-id>/runs/` | reserved (0.4.0) | studio | no |

### Studio files in general
Every file the studio writes is a versioned JSON **envelope** (`kind` + `schemaVersion`). It is written as UTF-8
without BOM, LF line ends, 2-space indent, sorted top-level keys and a trailing newline, and replaced atomically (temp
file + rename). When an older studio version wrote it, the file is migrated on open and the original is first copied
to `.backup/<file name>.v<old>.<UTC timestamp>.json` next to it. Unknown keys are kept. A file with a `schemaVersion`
newer than the studio supports is never rewritten. Details: [packages/config-schema/README.md](../../packages/config-schema/README.md).

## Opening a folder as a workspace

| The folder… | Result |
|---|---|
| does not exist | created and initialised (`.studio/` with the marker, `trash/`, `cache/`) |
| is empty (or holds only an incomplete `.studio/` with no marker) | initialised |
| has `.studio/workspace.json` | opened; files are not rewritten (an older marker is migrated) |
| has an unreadable marker (bad JSON, wrong content, newer version) | refused: `workspace_invalid`, nothing written |
| is not empty and has no marker | refused: `workspace_not_empty`, nothing written, so the studio never scatters files into someone's Documents folder |
| is a file | refused: `workspace_not_a_folder` |
| is open in another studio backend | refused: `workspace_in_use` |

Paths with spaces, non-ASCII characters and, on Windows, more than 260 characters are supported.

## Workspace lock
While a backend has a workspace open, it holds an **OS-level lock** on `.studio/lock` (`fcntl.flock` on Linux,
`msvcrt.locking` on Windows). A second backend that opens the same workspace gets `workspace_in_use` and writes
nothing. The OS drops the lock when the holding process ends, however it ends (killed, crashed), so a lock is never
stale and nobody needs to delete the file. Only one backend at a time works on a workspace (PO decision).

## Project ids
The project id is the project folder's name. It is chosen at creation and **immutable**: renaming a project changes
its display name (`name` in `project.json`), never its id or folder.

### Rules
A valid id:
1. is 1 to 64 characters long;
2. contains only lowercase `a-z`, digits `0-9` and `-`;
3. is not a name Windows reserves for files: `con`, `prn`, `aux`, `nul`, `com1`–`com9`, `lpt1`–`lpt9`;
4. is unique in the workspace, compared case-insensitively.

### Explicit ids
An id the user types is never altered. If it breaks a rule, creation fails with `invalid_project_id` naming the
broken rule; if it is taken, with `project_id_taken`.

### Derived ids
A project created from its display name only gets a derived id:
1. Unicode NFKD, drop combining marks, lowercase (`Équipe 7` → `equipe 7`);
2. every run of characters other than `a-z0-9` becomes `-`; trim `-` at both ends;
3. cut to 64 characters and trim `-` again;
4. empty result (`日本語`, `!!!`) → `project`;
5. a Windows reserved name (`Con` → `con`) gets `-project` (`con-project`);
6. a taken id gets `-2`, `-3`, … (shortened first so the result stays within 64 characters).

So `Équipe 7` → `equipe-7`, `Con` → `con-project`, a second `My project` → `my-project-2`. A derived id never fails
with `project_id_taken`.

## Other files and odd folders
- A folder **without `project.json`**, and any **dot-folder** (`.git`, `.studio`, `.hidden-project`), is not a
  project: it is not listed and is not an error. Users may keep other files in their workspace.
- A folder **with `project.json` but an invalid name** (e.g. `My Proj/`) is listed in an error state,
  `invalid_project_id`, and is read-only in the studio (it cannot be opened, edited, archived or deleted from the
  app). The message tells the user to rename the folder. The studio never renames user folders on its own.
- When `id` inside `project.json` differs from the folder name (e.g. a folder copied by hand), **the folder name
  wins**. The project is listed in the `file_invalid` state with the JSON pointer `/id`, so the user fixes it
  consciously.

## Delete and trash
Deleting a project moves its whole folder to `.studio/trash/<project-id>.<UTC timestamp>/`. The studio never uses
the OS recycle bin (portable, testable, no native dependency). Emptying the trash comes in a later version (0.7.0).

## Outside the workspace: app settings
The studio remembers the current workspace and the recently opened ones in `settings.json`
(`kind: "app-settings"`, [schema](../../packages/config-schema/schemas/app-settings.v1.schema.json)) in the OS user
config dir (`platformdirs`: `%APPDATA%\rlgym-studio\` on Windows, `~/.config/rlgym-studio/` on Linux).
`STUDIO_BACKEND_SETTINGS_DIR` overrides the folder. Only the backend reads or writes it. An unreadable settings file
is moved aside (`settings.json.<reason>.<timestamp>.json`) and the studio starts from empty settings.
