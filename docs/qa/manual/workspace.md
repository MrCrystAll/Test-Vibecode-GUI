# Manual procedures: workspace and projects (0.2.0)

Owner: `[QA]`. Referenced from [0.2.0-test-plan.md](../0.2.0-test-plan.md) §3. Run each procedure on **Windows and
Linux** when its story is In Test and at every 0.2.0 beta, unless it says otherwise. Record the OS, the tag, the
workspace path and the result of each numbered step in the Jira journal or the beta report.

Conventions:
- `<app-cmd>`: the documented dev launch of the desktop app (TC-23). `<backend-cmd>`: the documented backend
  command (`apps/backend/README.md`).
- `<ud1>`, `<ud2>`: two separate Electron user-data dirs, and `<sd1>`, `<sd2>` two `STUDIO_SETTINGS_DIR`s, so the
  instances share nothing but the workspace. Use the documented way to set them (env var or CLI flag, TC-23/TC-34).
- `<ws>`: a fresh copy of a fixture from `tests/fixtures/workspaces/`, made **before** each procedure into a folder
  whose path contains a space and a non-ASCII character, e.g. `C:\qa tmp é\ws` or `~/qa tmp é/ws`.
  Never run a procedure on the committed fixture itself.
- "Unchanged" means same bytes **and** same mtime. Windows: `Get-FileHash` + `(Get-Item f).LastWriteTimeUtc`.
  Linux: `sha256sum` + `stat -c %Y`.
- Edit files with a plain text editor (Notepad on Windows, `nano`/`gedit` on Linux) unless a step says to copy a
  prepared file from `tests/fixtures/edits/project-json/`.

## M-ED — hand-editing `project.json`
Covers X2-1, T-36-3, T-36-4, T-41-2, T-41-4. `<ws>` = copy of `external-edit`; project `edit-me`.

**A. While the app is closed**
1. Start the app on `<ws>`, check that `edit-me` and `bystander` are listed, quit. Confirm no backend process is left.
2. *Valid edit:* copy `edits/project-json/renamed.json` over `<ws>/edit-me/project.json`. Start the app.
   Expected: the list and the detail show name "Edited by hand" and the new description. No error, no toast.
   The file is unchanged (the app only reads it).
3. *Unknown key:* copy `extra-key.json` over it, start, then rename `edit-me` from the app to "Renamed in app".
   Expected: the file has the new name **and** still has `"userNote"`. It is written as UTF-8, LF, 2-space indent,
   with sorted keys.
4. *Invalid JSON:* quit, copy `invalid-json.json` over it, start. Expected: `edit-me` is listed with an error
   badge, a readable message and the file path, and it cannot be opened. `bystander` works normally. The file is
   unchanged. Nothing is created in `<ws>/edit-me/.backup/`.
5. *Newer studio:* quit, copy `too-new.json` over it, start. Expected: as in step 4, but the message says the file
   was written by a newer version of the studio (`file_too_new`). The file is unchanged.
6. *Notepad style (Windows, and Linux with the same file):* quit, copy `crlf-bom.json` over it, start. Expected
   (Q5): accepted like `renamed.json`, no error, file unchanged. Then rename the project from the app: the file
   comes back as UTF-8 without a BOM, with LF line endings.

**B. While the app is open** (from TC-37/TC-41)

7. With the list visible, apply `renamed.json` again. Expected: within about 2 s the row updates without a reload,
   and a toast says the project changed on disk.
8. Open `edit-me` in the detail view, apply `invalid-json.json`. Expected: the detail view shows the error state.
   It does not crash or show stale data as if it were valid.
9. Open the rename dialog for `bystander`, then edit `<ws>/bystander/project.json` by hand (change the name) and
   save. Back in the dialog, type a new name and submit. Expected: a "changed on disk, reload?" warning appears
   before anything is overwritten.
10. Delete the `<ws>/bystander/` folder in the file manager. Expected: the row disappears. If its detail view was
    open, it shows "removed outside the app".

## M-CACHE — deleting and corrupting `.studio/cache/`
Covers X2-3, T-37-1. `<ws>` = copy of `many-projects` (250 projects, 25 archived).

1. Start the app on `<ws>`. Record the counts under the Active/Archived/All filters (expected 225/25/250) and the
   first 5 rows of the list (sorted by last updated). Record the index rebuild time from the backend log. Quit.
2. Delete `<ws>/.studio/cache/` entirely. Start. Expected: identical counts and first rows, no error shown, the log
   says the index was rebuilt. Nothing under `<ws>/<project>/` changed (compare a hash listing taken in step 1).
3. Quit. Overwrite every file under `.studio/cache/` with garbage (e.g. the text `not an index`). If the cache has
   no files, record that and skip to step 5. Start. Expected: as in step 2, plus one log line about a discarded
   corrupt cache. No error dialog.
4. Quit. Delete one project folder by hand (e.g. `project-007`) and start. Expected: 249 projects. The stale cache
   must not bring it back.
5. Record the timings and results.

## M-TWO — two app instances on one workspace
Covers T-34-6, T-38-3. `<ws>` = copy of `one-project`.

1. Start instance A with `<ud1>`/`<sd1>` and open `<ws>`. The project list shows `first-project`.
2. Start instance B with `<ud2>`/`<sd2>` and choose `<ws>` in the first-run screen. Expected: a specific
   "workspace in use" message with a next step. B does not show the list. A keeps working (create a project in A
   to prove it).
3. Check `<ws>`: no file B could have written (no new project, `.studio/workspace.json` unchanged).
4. Quit A normally. In B, retry opening `<ws>`. Expected: it opens.
5. *Stale lock:* with B holding the workspace, kill B's backend process hard (Windows: `Stop-Process -Force` on the
   `python -m studio_backend` PID found with `Get-CimInstance Win32_Process`; Linux: `kill -9`), then quit B. Start
   A on `<ws>`. Expected: A opens the workspace. A lock left by a killed process must not block it.
6. Variant on one machine with the **same** user-data dir: the second launch focuses the first window (TC-24 AC3)
   and never reaches the workspace lock. Record it.

## M-KILL — killing the backend mid-write
Covers T-36-2. `<ws>` = copy of `one-project`. Needs a way to keep the backend writing: run this loop against the
backend of a running app (port and token from the app log or the handshake) or against `<backend-cmd>` started by
hand on `<ws>`.

1. In a shell, loop PATCH requests that rename `first-project` with an increasing counter (`name: "n-<i>"`),
   as fast as possible.
2. After a few seconds, kill the backend hard (as in M-TWO step 5) while the loop runs. Repeat steps 1–2 five
   times (restart the backend each time).
3. After each kill, check `<ws>/first-project/project.json`: it parses as JSON, validates against
   `packages/config-schema/schemas/project.v1.schema.json`, and its name is one of the names sent. No `*.tmp` or
   partial file remains in the folder, or, if the design leaves temp files after a crash, the next start removes
   them (record which).
4. Start the app. The project opens normally, with the last name that was written.

## M-PATH — hostile workspace paths (Windows)
Covers T-34-5. Linux gets the space + non-ASCII part through every automated test.

1. Record `LongPathsEnabled` (`(Get-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem).LongPathsEnabled`).
   The QA machine has `1`. A stock Windows 10 has `0`, and that is what most users have. **This procedure counts
   as passed only after a run with `0`** (a VM or the owner's machine; QA does not change system settings).
2. Create a folder whose full path is > 260 characters, with spaces and non-ASCII characters in several segments,
   e.g. `C:\qa long é\` + 12 × `segment ü 0123456789\`. Check its length with `(Resolve-Path .).Path.Length`.
3. Create a new workspace there from the first-run screen, create two projects, rename one, archive one, delete
   one.
4. Quit and restart. Expected: the workspace reopens directly, and every change from step 3 is there. The deleted
   project is under `.studio/trash/`. The workspace path in the app shell shows correctly.
5. Repeat steps 3–4 with a workspace whose path is just under 260 characters but whose `project.json` path passes
   260 (long project id, 64 chars).
6. Record any error with the full log line.

## M-EXP2 — exploratory charter for 0.2.0 (30 min per OS)
Rename and archive quickly in sequence. Create projects whose names slug to the same id, to an empty id, or to a
reserved name (`Con`, `NUL`). Edit files while dialogs are open. `git checkout` an older version of a workspace
under a running app. Put the workspace on a network share or a USB stick (exFAT), and check the watcher fallback
(`watching: false`). Open a workspace that is also open in VS Code, which writes `.vscode/` into it. Switch
workspaces repeatedly. Delete the workspace folder while the app runs. Fill the disk (small VHD / tmpfs) and save.
