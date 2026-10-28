// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from '@playwright/test';

const ci = Boolean(process.env['CI']);

export default defineConfig({
  testDir: './specs',
  outputDir: 'test-results',
  // Every test starts a real window and a real backend: one at a time keeps ports, focus and timing deterministic.
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  // Strategy §8: no retries locally; at most one on CI, and a pass-on-retry is still reported as flaky.
  retries: ci ? 1 : 0,
  forbidOnly: ci,
  reporter: ci ? [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]] : [['list']],
});
