// SPDX-License-Identifier: Apache-2.0
// Renderer isolation and log hygiene (test plan T-23-3, T-23-5).
import { expect, fakeBackendCommand, test } from '../../support/fixtures';

// The renderer-side API documented in apps/desktop/README.md (what the preload exposes, and nothing else).
const DOCUMENTED_BRIDGE = ['getBackendConnection', 'getStartupState', 'onStartupState', 'quit', 'retryBackend'];

test('the renderer has no Node access and only the documented bridge', {
  tag: ['@TC-23', '@TC-23-AC2'],
}, async ({ launchApp }) => {
  // Any backend will do: this test never needs the app to be ready, so use the one that just hangs.
  const studio = await launchApp({
    env: {
      STUDIO_BACKEND_CMD: fakeBackendCommand('hang', test.info().outputPath('fake-backend.pid')),
      STUDIO_BACKEND_STARTUP_TIMEOUT_MS: '60000',
    },
  });
  const page = studio.window;
  await expect(page.getByTestId('splash')).toBeVisible();

  const probe = await page.evaluate(() => {
    const global = window as unknown as Record<string, unknown>;
    const bridge = global['studio'] as Record<string, unknown> | undefined;
    return {
      require: typeof global['require'],
      process: typeof global['process'],
      module: typeof global['module'],
      electron: typeof global['electron'],
      bridgeKeys: bridge ? Object.keys(bridge).sort() : null,
      origin: location.origin,
    };
  });
  expect(probe.require).toBe('undefined');
  expect(probe.process).toBe('undefined');
  expect(probe.module).toBe('undefined');
  expect(probe.electron).toBe('undefined');
  expect(probe.bridgeKeys).toEqual(DOCUMENTED_BRIDGE);
  expect(probe.origin).toBe('studio://app');

  // And the window really was created with the secure settings, whatever the renderer can see.
  const prefs = await studio.electronApp.evaluate(({ BrowserWindow }) => {
    const [win] = BrowserWindow.getAllWindows();
    if (!win) {
      throw new Error('no window');
    }
    const contents = win.webContents as unknown as { getLastWebPreferences(): Record<string, unknown> };
    const { contextIsolation, sandbox, nodeIntegration } = contents.getLastWebPreferences();
    return { contextIsolation, sandbox, nodeIntegration };
  });
  expect(prefs).toEqual({ contextIsolation: true, sandbox: true, nodeIntegration: false });
});

test('the window refuses pop-ups and navigation away from the app', {
  tag: ['@TC-23', '@TC-23-AC2'],
}, async ({ launchApp }) => {
  const studio = await launchApp({
    env: {
      STUDIO_BACKEND_CMD: fakeBackendCommand('hang', test.info().outputPath('fake-backend.pid')),
      STUDIO_BACKEND_STARTUP_TIMEOUT_MS: '60000',
    },
  });
  const page = studio.window;
  await expect(page.getByTestId('splash')).toBeVisible();

  // Register a listener in the main process *after* the app's own handler, so it sees the final decision.
  await studio.electronApp.evaluate(({ BrowserWindow }) => {
    const [win] = BrowserWindow.getAllWindows();
    if (!win) {
      throw new Error('no window');
    }
    (globalThis as Record<string, unknown>)['qaNavigation'] = new Promise((resolve) => {
      win.webContents.once('will-navigate', (event, url) => {
        resolve({ url, prevented: event.defaultPrevented });
      });
    });
  });
  await page.evaluate(() => {
    window.open('https://example.com/', '_blank');
    location.href = 'https://example.com/';
  });
  // The navigation event is the synchronisation point: the pop-up request came first and was handled before it.
  const navigation = await studio.electronApp.evaluate(
    () => (globalThis as Record<string, unknown>)['qaNavigation'] as Promise<{ url: string; prevented: boolean }>,
  );

  expect(navigation).toEqual({ url: 'https://example.com/', prevented: true });
  expect(studio.electronApp.windows()).toHaveLength(1);
  // Look from inside the page: Playwright's locators wait for a navigation that Electron cancelled, and so never
  // completes. The page itself must be untouched: same address, same screen.
  const after = await page.evaluate(() => ({
    href: location.href,
    splash: document.querySelector('[data-testid="splash"]') !== null,
  }));
  expect(after.href).toMatch(/^studio:\/\/app\//);
  expect(after.splash).toBe(true);
});

test('the token reaches the renderer only through the bridge and never the logs', {
  tag: ['@TC-23', '@TC-23-AC4', '@TC-19', '@TC-19-AC5'],
}, async ({ launchApp }) => {
  const studio = await launchApp();
  await studio.window.getByTestId('nav-status').click();
  await expect(studio.window.getByTestId('status-health')).toHaveAttribute('data-state', 'healthy');

  const connection = await studio.window.evaluate(() =>
    (window as unknown as { studio: { getBackendConnection(): Promise<{ baseUrl: string; token: string }> } }).studio.getBackendConnection(),
  );
  expect(connection.baseUrl).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
  expect(connection.token.length).toBeGreaterThanOrEqual(22);

  // The shell's log and the backend's log live in the user-data folder, and neither contains the token.
  expect(studio.readLog('main.log')).toContain('backend started');
  // The backend's stderr (its JSON log lines) really is written to backend.log (TC-23 AC4).
  await expect.poll(() => studio.readLog('backend.log')).toMatch(/"level": ?"info"/);
  for (const name of ['main.log', 'backend.log'] as const) {
    expect(studio.readLog(name), `${name} must not contain the token`).not.toContain(connection.token);
  }
  // Nor is it in the page.
  expect(await studio.window.content()).not.toContain(connection.token);
});
