// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { waitForHealth } from './health';
import { IPC } from './ipc';
import { killPlan } from './process-tree';

describe('waitForHealth', () => {
  function clock() {
    let t = 0;
    return { now: () => t, sleep: async (ms: number) => void (t += ms) };
  }

  it('returns true once /api/health answers 200', async () => {
    const answers = [new TypeError('ECONNREFUSED'), new Response('', { status: 503 }), new Response('{}')];
    const urls: string[] = [];
    const fetch = async (url: string | URL | Request) => {
      urls.push(String(url));
      const next = answers.shift();
      if (next instanceof Error) {
        throw next;
      }
      return next as Response;
    };

    expect(await waitForHealth({ baseUrl: 'http://127.0.0.1:5000', deadline: 10_000, fetch, ...clock() })).toBe(
      true,
    );
    expect(urls).toEqual(Array(3).fill('http://127.0.0.1:5000/api/health'));
  });

  it('returns false at the deadline', async () => {
    const fetch = async () => {
      throw new TypeError('ECONNREFUSED');
    };

    expect(await waitForHealth({ baseUrl: 'http://x', deadline: 1000, intervalMs: 200, fetch, ...clock() })).toBe(
      false,
    );
  });

  it('stops when cancelled', async () => {
    let calls = 0;
    const fetch = async () => {
      calls += 1;
      throw new TypeError('ECONNREFUSED');
    };

    await waitForHealth({ baseUrl: 'http://x', deadline: 1e9, fetch, cancelled: () => calls >= 2, ...clock() });

    expect(calls).toBe(2);
  });
});

describe('killPlan', () => {
  it('kills the whole tree with taskkill /T on Windows (uv -> launcher -> python)', () => {
    expect(killPlan('win32', 1234)).toEqual({ command: 'taskkill', args: ['/PID', '1234', '/T', '/F'] });
  });

  it('signals the process group on Linux', () => {
    expect(killPlan('linux', 1234)).toEqual({ signalGroup: -1234 });
  });
});

describe('IPC channels', () => {
  it('are the same in main (ipc.ts) and in the sandboxed preload, which cannot import them', () => {
    const preload = fs.readFileSync(path.join(__dirname, 'preload.ts'), 'utf8');

    for (const [key, channel] of Object.entries(IPC)) {
      expect(preload).toContain(`${key}: '${channel}'`);
    }
  });
});
