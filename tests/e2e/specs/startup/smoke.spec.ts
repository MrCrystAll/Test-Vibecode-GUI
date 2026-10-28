// SPDX-License-Identifier: Apache-2.0
// Exit criterion X-2 and test plan T-29-1, T-29-2, T-23-1, T-24-4 (quit part).
import fs from 'node:fs';

import { expect, expectGone, test } from '../../support/fixtures';

test('app starts, System status is healthy, and quitting leaves no backend', {
  tag: ['@TC-29', '@TC-29-AC2', '@TC-23', '@TC-23-AC1', '@X-2'],
}, async ({ launchApp }) => {
  const studio = await launchApp();
  const page = studio.window;

  // The shell opens the window at once; the UI replaces the splash once the backend answered /api/health.
  await page.getByTestId('nav-status').click();
  await expect(page.getByTestId('status-health')).toHaveAttribute('data-state', 'healthy');
  await expect(page.getByTestId('status-version')).toContainText('App ');

  // The shell logged the real python's pid (not uv's) and the port.
  await expect.poll(() => studio.backendInfo()).not.toBeNull();
  const backend = studio.backendInfo();
  if (!backend) {
    throw new Error('main.log has no "backend started" line');
  }
  expect(backend.pid).toBeGreaterThan(0);
  expect(backend.port).toBeGreaterThan(0);

  await studio.quit();

  // After quit: that python is gone and nothing listens on its port any more.
  await expectGone(backend);
});

test('each test gets its own empty user-data folder with a space and a non-ASCII character', {
  tag: ['@TC-29', '@TC-29-AC1'],
}, async ({ launchApp }) => {
  const first = await launchApp();
  const second = await launchApp();

  expect(first.userData).not.toBe(second.userData);
  for (const studio of [first, second]) {
    expect(studio.userData).toMatch(/ /);
    expect(studio.userData).toMatch(/é/);
    // The app wrote its logs into its own folder, not into a shared profile.
    await expect.poll(() => fs.existsSync(`${studio.logsDir}/main.log`)).toBe(true);
  }
});
