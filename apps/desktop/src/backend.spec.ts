// SPDX-License-Identifier: Apache-2.0
// BackendSupervisor against a real child process (testing/fake-backend.cjs): stop, force-kill, crash and restart.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { PassThrough } from 'node:stream';

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { BackendSupervisor } from './backend';
import { readPidFile } from './pid-file';
import { isAlive } from './process-tree';
import type { StartupState } from './startup';

const FAKE_BACKEND = path.join(__dirname, 'testing', 'fake-backend.cjs');

describe('BackendSupervisor lifecycle (TC-24)', () => {
  let dir: string;
  let logs: string[];
  let supervisor: BackendSupervisor | null;

  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-backend-'));
    logs = [];
    supervisor = null;
  });
  afterEach(async () => {
    await supervisor?.stop();
    fs.rmSync(dir, { recursive: true, force: true });
  });

  function start(mode: 'normal' | 'ignore-stdin' = 'normal', gracefulMs = 5000): BackendSupervisor {
    supervisor = new BackendSupervisor({
      command: [process.execPath, FAKE_BACKEND, mode],
      cwd: dir,
      env: {},
      startupTimeoutMs: 10_000,
      backendLog: new PassThrough(),
      log: (message) => void logs.push(message),
      pidFile: path.join(dir, 'backend.pid'),
      gracefulMs,
    });
    supervisor.start();
    return supervisor;
  }

  function reach(backend: BackendSupervisor, phase: StartupState['phase']): Promise<StartupState> {
    return new Promise((resolve) => {
      if (backend.current.phase === phase) {
        resolve(backend.current);
        return;
      }
      const off = backend.onChange((state) => {
        if (state.phase === phase) {
          off();
          resolve(state);
        }
      });
    });
  }

  function handshakeOf(state: StartupState) {
    if (state.phase !== 'ready') {
      throw new Error(`not ready: ${state.phase}`);
    }
    return state.handshake;
  }

  it('records the PIDs while running and stops gracefully through stdin', async () => {
    const backend = start();
    const { pid } = handshakeOf(await reach(backend, 'ready'));
    expect(readPidFile(path.join(dir, 'backend.pid'))).toMatchObject({ servingPid: pid });

    await backend.stop();

    expect(isAlive(pid)).toBe(false);
    expect(logs.join('\n')).toContain('backend stop: graceful');
    expect(fs.existsSync(path.join(dir, 'backend.pid'))).toBe(false);
    expect(backend.current.phase).toBe('ready'); // a requested stop is not a crash
  });

  it('kills a backend that ignores the shutdown signal', async () => {
    const backend = start('ignore-stdin', 300);
    const { pid } = handshakeOf(await reach(backend, 'ready'));

    await backend.stop();

    expect(isAlive(pid)).toBe(false);
    expect(logs.join('\n')).toContain('backend stop: killed');
  });

  it('reports a crash as stopped, and restarts on a new port with a new token', async () => {
    const backend = start();
    const first = handshakeOf(await reach(backend, 'ready'));

    await fetch(`http://127.0.0.1:${first.port}/crash`).catch(() => undefined);
    expect(await reach(backend, 'stopped')).toMatchObject({ detail: 'backend exited with code 7' });

    const restarting = backend.retry();
    const second = handshakeOf(await reach(backend, 'ready'));
    await restarting;

    expect(second.pid).not.toBe(first.pid);
    expect(second.token).not.toBe(first.token);
    expect(second.port).not.toBe(first.port);
    expect(logs.join('\n')).toContain('backend stopped unexpectedly');
  });
});
