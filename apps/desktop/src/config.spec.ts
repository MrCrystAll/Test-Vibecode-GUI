// SPDX-License-Identifier: Apache-2.0
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { DEFAULT_BACKEND_COMMAND, DEFAULT_STARTUP_TIMEOUT_MS, parseLaunchConfig, repoRootFrom } from './config';

const ROOT = path.resolve('/repo');

describe('parseLaunchConfig', () => {
  it('defaults to the dev backend via uv, the built UI and a sandboxed renderer', () => {
    expect(parseLaunchConfig(['electron', '.'], {}, ROOT)).toEqual({
      userDataDir: null,
      uiUrl: null,
      backendCommand: DEFAULT_BACKEND_COMMAND,
      backendCwd: ROOT,
      startupTimeoutMs: DEFAULT_STARTUP_TIMEOUT_MS,
      noSandbox: false,
    });
  });

  it('takes the user-data dir from the flag first, then the environment (TC-29 isolation)', () => {
    const env = { STUDIO_USER_DATA_DIR: '/from-env' };

    expect(parseLaunchConfig(['electron', '.', '--user-data-dir=/from-flag'], env, ROOT).userDataDir).toBe(
      '/from-flag',
    );
    expect(parseLaunchConfig(['electron', '.'], env, ROOT).userDataDir).toBe('/from-env');
  });

  it('reads the dev/test overrides', () => {
    const config = parseLaunchConfig(
      ['electron', '.'],
      {
        STUDIO_UI_URL: 'http://localhost:4200',
        STUDIO_BACKEND_CMD: '["python", "fake_backend.py"]',
        STUDIO_BACKEND_STARTUP_TIMEOUT_MS: '500',
        STUDIO_E2E_NO_SANDBOX: '1',
      },
      ROOT,
    );

    expect(config).toMatchObject({
      uiUrl: 'http://localhost:4200',
      backendCommand: ['python', 'fake_backend.py'],
      startupTimeoutMs: 500,
      noSandbox: true,
    });
  });

  it('only disables the sandbox for exactly STUDIO_E2E_NO_SANDBOX=1', () => {
    expect(parseLaunchConfig([], { STUDIO_E2E_NO_SANDBOX: 'true' }, ROOT).noSandbox).toBe(false);
  });

  it.each([
    [{ STUDIO_BACKEND_CMD: '"uv run"' }, 'STUDIO_BACKEND_CMD'],
    [{ STUDIO_BACKEND_CMD: '[]' }, 'STUDIO_BACKEND_CMD'],
    [{ STUDIO_BACKEND_CMD: '["uv", ""]' }, 'STUDIO_BACKEND_CMD'],
    [{ STUDIO_BACKEND_STARTUP_TIMEOUT_MS: '0' }, 'STUDIO_BACKEND_STARTUP_TIMEOUT_MS'],
    [{ STUDIO_BACKEND_STARTUP_TIMEOUT_MS: 'soon' }, 'STUDIO_BACKEND_STARTUP_TIMEOUT_MS'],
  ])('rejects invalid overrides %j', (env, name) => {
    expect(() => parseLaunchConfig([], env, ROOT)).toThrow(name);
  });
});

describe('repoRootFrom', () => {
  it('goes from apps/desktop/dist to the repository root', () => {
    expect(repoRootFrom(path.join(ROOT, 'apps', 'desktop', 'dist'))).toBe(ROOT);
  });
});
