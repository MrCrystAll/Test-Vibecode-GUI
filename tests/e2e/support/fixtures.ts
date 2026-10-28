// SPDX-License-Identifier: Apache-2.0
// `launchApp` fixture: every test gets its own app, user-data folder and evidence handling (strategy §5.2).
import { expect, test as base } from '@playwright/test';
import path from 'node:path';

import { REPO_ROOT, StudioApp, isPortOpen, isProcessAlive, type LaunchOptions } from './app';

interface Fixtures {
  launchApp: (options?: LaunchOptions) => Promise<StudioApp>;
}

export const test = base.extend<Fixtures>({
  // Playwright wants a destructuring pattern as the first argument, even when no fixture is used.
  // eslint-disable-next-line no-empty-pattern
  launchApp: async ({}, use, testInfo) => {
    const apps: StudioApp[] = [];
    await use(async (options) => {
      const app = await StudioApp.launch(options);
      apps.push(app);
      return app;
    });
    for (const app of apps) {
      await app.dispose(testInfo);
    }
  },
});

export { expect };

/** Assert that a process is gone and nothing listens on its port, waiting for the OS to finish the job. */
export async function expectGone(target: { pid: number; port?: number }): Promise<void> {
  await expect.poll(() => isProcessAlive(target.pid), { message: `process ${target.pid} is still running` }).toBe(false);
  if (target.port !== undefined) {
    await expect.poll(() => isPortOpen(target.port as number), { message: `port ${target.port} is still open` }).toBe(false);
  }
}

/** Command line (JSON array) for STUDIO_BACKEND_CMD that runs the QA fake backend (tests/fixtures/fake-backend). */
export function fakeBackendCommand(mode: FakeBackendMode, pidFile: string): string {
  const script = path.join(REPO_ROOT, 'tests', 'fixtures', 'fake-backend', 'fake-backend.cjs');
  return JSON.stringify([process.execPath, script, '--mode', mode, '--pid-file', pidFile]);
}

export type FakeBackendMode = 'exit' | 'hang' | 'noise' | 'wrong-json' | 'stubborn';
