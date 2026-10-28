// SPDX-License-Identifier: Apache-2.0
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { type CleanupEffects, cleanUpOrphans, readPidFile, writePidFile } from './pid-file';
import { isAlive, killTree, waitForExit } from './process-tree';
import { type StopEffects, stopBackend } from './shutdown';

/** Records every effect in order; `exitsAfterSignal` says whether the backend honours the stdin signal. */
function fakeEffects(options: { exitsAfterSignal: boolean; survivesKill?: boolean }) {
  const calls: string[] = [];
  let signalled = false;
  let killed = false;
  const effects: StopEffects = {
    closeStdin: () => {
      calls.push('close-stdin');
      signalled = true;
    },
    waitForExit: async (pids, timeoutMs) => {
      calls.push(`wait ${pids.join(',')} ${timeoutMs}`);
      if (killed) {
        return !options.survivesKill;
      }
      return signalled && options.exitsAfterSignal;
    },
    killTree: async (pid) => {
      calls.push(`kill ${pid}`);
      killed = true;
    },
  };
  return { calls, effects };
}

describe('stopBackend (TC-24 AC1)', () => {
  it('asks gracefully first, and kills nothing when the backend exits in time', async () => {
    const { calls, effects } = fakeEffects({ exitsAfterSignal: true });

    expect(await stopBackend({ spawnedPid: 10, servingPid: 42 }, effects, 5000)).toBe('graceful');
    expect(calls).toEqual(['close-stdin', 'wait 10,42 5000']);
  });

  it('kills the spawned tree and the serving PID after the graceful timeout, then checks they are gone', async () => {
    const { calls, effects } = fakeEffects({ exitsAfterSignal: false });

    expect(await stopBackend({ spawnedPid: 10, servingPid: 42 }, effects, 5000)).toBe('killed');
    expect(calls).toEqual(['close-stdin', 'wait 10,42 5000', 'kill 10', 'kill 42', 'wait 10,42 3000']);
  });

  it('kills at once before the handshake: nothing is serving yet', async () => {
    const { calls, effects } = fakeEffects({ exitsAfterSignal: true });

    expect(await stopBackend({ spawnedPid: 10, servingPid: null }, effects)).toBe('killed');
    expect(calls).toEqual(['kill 10', 'wait 10 3000']);
  });

  it('still stops the serving python when uv already exited (orphan on Windows)', async () => {
    const { calls, effects } = fakeEffects({ exitsAfterSignal: false });

    expect(await stopBackend({ spawnedPid: null, servingPid: 42 }, effects, 100)).toBe('killed');
    expect(calls).toEqual(['close-stdin', 'wait 42 100', 'kill 42', 'wait 42 3000']);
  });

  it('reports a process that survives the kill', async () => {
    const { effects } = fakeEffects({ exitsAfterSignal: false, survivesKill: true });

    expect(await stopBackend({ spawnedPid: 10, servingPid: 42 }, effects, 1)).toBe('survived');
  });

  it('does nothing when no backend runs', async () => {
    const { calls, effects } = fakeEffects({ exitsAfterSignal: true });

    expect(await stopBackend({ spawnedPid: null, servingPid: null }, effects)).toBe('graceful');
    expect(calls).toEqual([]);
  });
});

describe('waitForExit', () => {
  function clock() {
    let t = 0;
    return { now: () => t, sleep: async (ms: number) => void (t += ms) };
  }

  it('resolves true once every PID is gone', async () => {
    let checks = 0;
    const isAlive = (pid: number) => pid === 42 && ++checks < 4;

    expect(await waitForExit([10, 42], 1000, { isAlive, ...clock() })).toBe(true);
  });

  it('resolves false at the timeout', async () => {
    expect(await waitForExit([42], 200, { isAlive: () => true, intervalMs: 50, ...clock() })).toBe(false);
  });
});

describe('killTree', () => {
  it('kills a process that does not lead its own group, like the serving python (DEV-A, #32)', async () => {
    const child = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' });
    const pid = child.pid as number;
    const exited = new Promise((resolve) => child.once('exit', resolve));

    await killTree(pid);
    await exited;

    expect(isAlive(pid)).toBe(false);
  });
});

describe('PID file and orphan clean-up (TC-24 AC4)', () => {
  let dir: string;
  let file: string;

  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-pid-'));
    file = path.join(dir, 'backend.pid');
  });
  afterEach(() => fs.rmSync(dir, { recursive: true, force: true }));

  function effects(alive: Record<number, string | null>): CleanupEffects & { killed: number[]; logs: string[] } {
    const killed: number[] = [];
    const logs: string[] = [];
    return {
      killed,
      logs,
      isAlive: (pid) => pid in alive,
      commandLineOf: async (pid) => alive[pid] ?? null,
      killTree: async (pid) => void killed.push(pid),
      log: (message) => void logs.push(message),
    };
  }

  it('round-trips the record', () => {
    writePidFile(file, { spawnedPid: 10, servingPid: 42 });

    expect(readPidFile(file)).toEqual({ spawnedPid: 10, servingPid: 42 });
  });

  it('kills a leftover backend, serving python first, and deletes the file', async () => {
    writePidFile(file, { spawnedPid: 10, servingPid: 42 });
    const fx = effects({
      10: 'uv run --package studio-backend studio-backend',
      42: 'C:\\repo\\.venv\\Scripts\\python.exe C:\\repo\\.venv\\Scripts\\studio-backend.exe',
    });

    expect(await cleanUpOrphans(file, fx)).toEqual([42, 10]);
    expect(fx.killed).toEqual([42, 10]);
    expect(fs.existsSync(file)).toBe(false);
  });

  it('leaves alone a PID that now belongs to another program', async () => {
    writePidFile(file, { spawnedPid: 10, servingPid: 42 });
    const fx = effects({ 42: 'C:\\Windows\\notepad.exe' });

    expect(await cleanUpOrphans(file, fx)).toEqual([]);
    expect(fx.killed).toEqual([]);
    expect(fx.logs.join('\n')).toContain('pid=42 is no longer a studio backend');
    expect(fs.existsSync(file)).toBe(false);
  });

  it('does nothing without a PID file, or with a corrupt one', async () => {
    const fx = effects({ 42: 'studio_backend' });
    expect(await cleanUpOrphans(file, fx)).toEqual([]);

    fs.writeFileSync(file, 'not json');
    expect(await cleanUpOrphans(file, fx)).toEqual([]);
    expect(fx.killed).toEqual([]);
  });
});
