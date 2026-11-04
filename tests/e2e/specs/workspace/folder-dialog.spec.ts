// SPDX-License-Identifier: Apache-2.0
// Native folder dialog through the test hook (TC-46; test plan T-38-2, TC-43 AC2).
import path from 'node:path';

import { expect, test } from '../../support/fixtures';

interface Bridge {
  selectDirectory: () => Promise<string | null>;
}

const HOOK_LOG = 'test mode: selectDirectory answered by STUDIO_E2E_SELECT_DIRECTORY';

test('selectDirectory answers the hook path, with a space and a non-ASCII character', {
  tag: ['@TC-46', '@TC-46-AC4'],
}, async ({ launchApp }) => {
  const chosen = path.join(process.cwd(), 'studio é ws');
  const studio = await launchApp({ env: { STUDIO_E2E: '1', STUDIO_E2E_SELECT_DIRECTORY: chosen } });
  const page = studio.window;

  const answer = await page.evaluate(() => (window as unknown as { studio: Bridge }).studio.selectDirectory());
  expect(answer).toBe(chosen);
  expect(studio.readLog('main.log')).toContain(HOOK_LOG);
});

test('the hook value __cancel__ answers null, as if the user cancelled', {
  tag: ['@TC-46', '@TC-46-AC1', '@TC-46-AC4'],
}, async ({ launchApp }) => {
  const studio = await launchApp({ env: { STUDIO_E2E: '1', STUDIO_E2E_SELECT_DIRECTORY: '__cancel__' } });
  const page = studio.window;

  const answer = await page.evaluate(() => (window as unknown as { studio: Bridge }).studio.selectDirectory());
  expect(answer).toBeNull();
});

test('without STUDIO_E2E=1 the hook is ignored (the real dialog would open)', {
  tag: ['@TC-46', '@TC-46-AC4'],
}, async ({ launchApp }) => {
  // Not calling selectDirectory() here: it would open a native dialog nobody can close. The shell's log is the evidence.
  const studio = await launchApp({ env: { STUDIO_E2E_SELECT_DIRECTORY: '/should/be/ignored' } });
  await expect(studio.window.getByTestId('splash').or(studio.window.getByTestId('nav-status'))).toBeVisible();
  expect(studio.readLog('main.log')).not.toContain(HOOK_LOG);
});

test('the bridge exposes selectDirectory as the only folder access, and it is a function', {
  tag: ['@TC-46', '@TC-46-AC1', '@TC-46-AC2'],
}, async ({ launchApp }) => {
  const studio = await launchApp();
  const page = studio.window;
  const probe = await page.evaluate(() => {
    const bridge = (window as unknown as { studio: Record<string, unknown> }).studio;
    return { type: typeof bridge['selectDirectory'], fs: typeof (window as unknown as Record<string, unknown>)['require'] };
  });
  expect(probe).toEqual({ type: 'function', fs: 'undefined' });
});
