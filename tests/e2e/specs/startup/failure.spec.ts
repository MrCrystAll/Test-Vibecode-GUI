// SPDX-License-Identifier: Apache-2.0
// Startup failures: splash, error dialog with Retry and Quit, nothing left behind (test plan T-23-2, T-23-4).
import fs from 'node:fs';

import { type StudioApp } from '../../support/app';
import {
  expect,
  expectGone,
  fakeBackendCommand,
  test,
  type FakeBackendMode,
} from '../../support/fixtures';

/** Start the app with the fake backend in `mode`; returns it and the file the fake wrote its pid to. */
async function launchWithFake(
  launchApp: (options?: { env?: Record<string, string> }) => Promise<StudioApp>,
  mode: FakeBackendMode,
  extraEnv: Record<string, string> = {},
): Promise<{ studio: StudioApp; pidFile: string }> {
  const pidFile = test.info().outputPath('fake-backend.pid');
  const studio = await launchApp({
    env: { STUDIO_BACKEND_CMD: fakeBackendCommand(mode, pidFile), ...extraEnv },
  });
  return { studio, pidFile };
}

function readPid(pidFile: string): number {
  return Number(fs.readFileSync(pidFile, 'utf-8'));
}

const reasons: { mode: FakeBackendMode; reason: string; title: string }[] = [
  { mode: 'exit', reason: 'exited', title: 'a backend that exits at once' },
  { mode: 'noise', reason: 'bad-handshake', title: 'a first line that is not JSON' },
  { mode: 'wrong-json', reason: 'bad-handshake', title: 'a first line that is not the handshake' },
];

for (const { mode, reason, title } of reasons) {
  test(`${title} shows the startup error (${reason}) with Retry and Quit`, {
    tag: ['@TC-23', '@TC-23-AC3'],
  }, async ({ launchApp }) => {
    const { studio, pidFile } = await launchWithFake(launchApp, mode);
    const page = studio.window;

    await expect(page.getByTestId('startup-error')).toBeVisible();
    await expect(page.getByTestId('startup-error-reason')).toHaveAttribute('data-reason', reason);
    await expect(page.getByTestId('startup-error-retry')).toBeVisible();
    await expect(page.getByTestId('startup-error-quit')).toBeVisible();
    await expect(page.getByTestId('splash')).toHaveCount(0);
    expect(studio.readLog('main.log')).toContain(`backend startup failed: ${reason}`);
    // A failed attempt never leaves its process running.
    await expectGone({ pid: readPid(pidFile) });
  });
}

test('a backend command that cannot be spawned shows spawn-error', {
  tag: ['@TC-23', '@TC-23-AC3'],
}, async ({ launchApp }) => {
  const studio = await launchApp({ env: { STUDIO_BACKEND_CMD: JSON.stringify(['qa-no-such-command-e2e']) } });

  await expect(studio.window.getByTestId('startup-error-reason')).toHaveAttribute('data-reason', 'spawn-error');
  await expect(studio.window.getByTestId('startup-error-retry')).toBeVisible();
});

test('a backend that never answers hits the startup timeout and is killed', {
  tag: ['@TC-23', '@TC-23-AC1', '@TC-23-AC3'],
}, async ({ launchApp }) => {
  const { studio, pidFile } = await launchWithFake(launchApp, 'hang', {
    STUDIO_BACKEND_STARTUP_TIMEOUT_MS: '2000',
  });

  await expect(studio.window.getByTestId('startup-error-reason')).toHaveAttribute('data-reason', 'timeout');
  await expectGone({ pid: readPid(pidFile) });
});

test('the splash is shown while the backend is starting', { tag: ['@TC-23', '@TC-23-AC3'] }, async ({ launchApp }) => {
  const { studio } = await launchWithFake(launchApp, 'hang', { STUDIO_BACKEND_STARTUP_TIMEOUT_MS: '60000' });

  await expect(studio.window.getByTestId('splash')).toBeVisible();
  await expect(studio.window.getByTestId('startup-error')).toHaveCount(0);
});

test('Retry starts the backend command again', { tag: ['@TC-23', '@TC-23-AC3'] }, async ({ launchApp }) => {
  const { studio } = await launchWithFake(launchApp, 'exit');
  const starts = () => (studio.readLog('main.log').match(/backend starting/g) ?? []).length;
  await expect(studio.window.getByTestId('startup-error')).toBeVisible();
  expect(starts()).toBe(1);

  await studio.window.getByTestId('startup-error-retry').click();

  await expect.poll(starts).toBe(2);
  // The fake fails again, so the dialog comes back instead of the app hanging on the splash.
  await expect(studio.window.getByTestId('startup-error')).toBeVisible();
});

test('Quit from the error dialog ends the app and leaves no process behind', {
  tag: ['@TC-23', '@TC-23-AC3', '@TC-24', '@TC-24-AC4'],
}, async ({ launchApp }) => {
  const { studio, pidFile } = await launchWithFake(launchApp, 'noise');
  await expect(studio.window.getByTestId('startup-error')).toBeVisible();
  const closed = studio.electronApp.waitForEvent('close');

  await studio.window.getByTestId('startup-error-quit').click();

  await closed;
  await expectGone({ pid: readPid(pidFile) });
});
