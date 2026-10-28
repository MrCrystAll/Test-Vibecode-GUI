# tests/e2e: end-to-end suite

**Owner:** QA (`[QA]`). **Language:** TypeScript (pnpm workspace member `@studio/e2e`).
Strategy: [docs/process/test-strategy.md](../../docs/process/test-strategy.md) §2-§5. Story: TC-29.

Playwright launches the **real desktop app** (Electron, `apps/desktop`) with a real backend and drives it through its
UI, the way a user does. It is black-box: nothing is imported from `apps/` or `packages/`. The app is observed through
the window, the log files in its user-data folder and the operating system (is a process still running? is a port still
open?).

## Run it

From the repository root, after `pnpm install` and `uv sync --all-packages`:

```bash
pnpm --filter @studio/ui build && pnpm --filter @studio/desktop build   # the app must be built first
pnpm --filter @studio/e2e run e2e                                       # the whole suite
pnpm --filter @studio/e2e exec playwright test specs/startup -g "Retry" # one spec / one test
uv run --no-project python tools/ci/run.py e2e                          # what CI runs (after `build`)
```

- **A window opens on your screen** for every test (a second or two each). Do not click in it while a test runs.
- **Linux without a display:** `xvfb-run --auto-servernum pnpm --filter @studio/e2e run e2e`, with
  `STUDIO_E2E_NO_SANDBOX=1` in containers where Chromium's sandbox helper is not installed (CI does both).
- `e2e` is deliberately not called `test`, so `pnpm -r test` and `run.py all` never launch Electron.
- Lint and types: `pnpm --filter @studio/e2e lint` and `typecheck` (run by CI's `checks` job).

## Layout

```
tests/e2e/
  playwright.config.ts   one worker, 90 s per test, no retries locally, one retry on CI (strategy §8)
  support/app.ts         StudioApp: launches the app, reads its logs, quits it, proves the backend is gone
  support/fixtures.ts    `test` with the `launchApp` fixture; `expectGone`, `fakeBackendCommand`
  specs/<feature>/<behaviour>.spec.ts
tests/fixtures/fake-backend/fake-backend.cjs   a deliberately broken backend for startup-failure tests
```

## Rules (what makes a test acceptable)

1. **Select by `data-testid` only**, never by CSS class or visible text: all strings are translatable. If the UI lacks
   an id you need, ask the UI developer to add it (and say so in the PR); do not select by text as a workaround.
2. **No sleeps.** Wait for a condition: `await expect(locator)...`, `expect.poll(...)`, or an event. ESLint rejects
   `waitForTimeout`.
3. **Every test gets its own app, user-data folder and backend** from the `launchApp` fixture. The folder is created
   under the system temp dir with a **space and a non-ASCII character** in its name (`studio e2é …`), so path bugs show
   up on both OSes. It is deleted when the test passes and **kept (path printed) when it fails**.
4. **Tag every test with its ticket and acceptance criterion**: `tag: ['@TC-23', '@TC-23-AC3']`. `grep -r "TC-23" specs`
   lists a story's tests, `playwright test --grep @TC-23` runs them.
5. **Check clean-up, not only behaviour.** A test that quits the app asserts that the backend it started is gone:
   `await expectGone({ pid, port })`.
6. **Never skip a test silently.** A flaky test gets a Jira Bug (label `flaky`) and `@quarantine` with the key in its
   title (strategy §8).

## Writing a new test

```ts
// specs/projects/list.spec.ts
import { expect, test } from '../../support/fixtures';

test('the project list shows the workspace projects', { tag: ['@TC-39', '@TC-39-AC1'] }, async ({ launchApp }) => {
  const studio = await launchApp();            // own user-data folder, real backend
  const page = studio.window;                  // name it `page` in specs: `window` is also a browser global

  await page.getByTestId('nav-projects').click();
  await expect(page.getByTestId('project-row')).toHaveCount(3);
});
```

`launchApp({ env })` passes environment variables to the app. The useful ones are in
[apps/desktop/README.md](../../apps/desktop/README.md): `STUDIO_BACKEND_CMD` (a JSON array: the command that replaces the
backend), `STUDIO_BACKEND_STARTUP_TIMEOUT_MS`, `STUDIO_UI_URL`.

What `StudioApp` gives you: `window` (Playwright `Page`), `electronApp`, `userData`, `readLog('main.log' | 'backend.log')`,
`backendInfo()` (pid and port from `main.log`), `quit()` (like Quit in a menu), `closeWindow()` (the title-bar ✕).
In `page.evaluate` callbacks `window` is the browser's: keep the Playwright page in a variable called `page`.

### Failing on purpose: the fake backend
`fakeBackendCommand(mode, pidFile)` builds a `STUDIO_BACKEND_CMD` for `tests/fixtures/fake-backend`: `exit`, `hang`
(prints nothing), `noise` (first line is not JSON), `wrong-json` (JSON that is not the handshake). It writes its own pid
to `pidFile`, so a test can assert it was killed. Use the real backend for everything that is not a startup failure.

## When a test fails
CI uploads `e2e-report-<os>` (HTML report, traces, screenshots, `main.log`, `backend.log`). Locally, the output folder is
`tests/e2e/test-results/`: open a trace with `pnpm --filter @studio/e2e exec playwright show-trace <trace.zip>`, and look
in the kept user-data folder (path printed) for `logs/main.log` and `logs/backend.log`.

## Known quirks
- `expect(locator)` waits for a navigation that Electron cancelled and never completes: after a blocked navigation,
  check the page with `page.evaluate` (see `specs/security/renderer.spec.ts`).
- On Windows, Chromium's helper processes keep the profile folder open for a moment after the main process dies, so
  clean-up ends the whole process tree (`taskkill /T`) and retries the delete.
