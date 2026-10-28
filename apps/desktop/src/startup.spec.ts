// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';

import { INITIAL_STATE, type StartupEvent, type StartupState, nextState, publicState } from './startup';

const HANDSHAKE = { port: 5000, token: 'secret', pid: 42 };
const run = (events: StartupEvent[], from: StartupState = INITIAL_STATE) => events.reduce(nextState, from);

describe('startup state machine', () => {
  it('goes starting -> waiting-health -> ready', () => {
    const waiting = run([{ type: 'handshake', handshake: HANDSHAKE }]);
    expect(waiting).toEqual({ phase: 'waiting-health', handshake: HANDSHAKE });

    expect(nextState(waiting, { type: 'health-ok' })).toEqual({ phase: 'ready', handshake: HANDSHAKE });
  });

  it('fails on a bad handshake', () => {
    expect(run([{ type: 'bad-handshake', detail: 'not JSON' }])).toEqual({
      phase: 'failed',
      reason: 'bad-handshake',
      detail: 'not JSON',
    });
  });

  it('fails when the backend cannot be spawned', () => {
    expect(run([{ type: 'spawn-error', detail: 'spawn uv ENOENT' }])).toMatchObject({
      phase: 'failed',
      reason: 'spawn-error',
    });
  });

  it.each<StartupEvent[]>([
    [],
    [{ type: 'handshake', handshake: HANDSHAKE }],
  ])('fails when the backend exits before it is ready (after %j)', (...before) => {
    expect(run([...before, { type: 'exited', code: 1, signal: null }])).toEqual({
      phase: 'failed',
      reason: 'exited',
      detail: 'backend exited with code 1',
    });
  });

  it('is stopped (not failed) when the backend dies after being ready', () => {
    const ready = run([{ type: 'handshake', handshake: HANDSHAKE }, { type: 'health-ok' }]);

    const stopped = nextState(ready, { type: 'exited', code: 3221225786, signal: null });

    expect(stopped).toEqual({ phase: 'stopped', detail: 'backend exited with code 3221225786' });
    expect(publicState(stopped)).toEqual({ phase: 'stopped' });
    expect(nextState(stopped, { type: 'exited', code: null, signal: 'SIGKILL' })).toBe(stopped);
    expect(nextState(stopped, { type: 'timeout', afterMs: 1 })).toBe(stopped);
    expect(nextState(stopped, { type: 'spawn-error', detail: 'late' })).toBe(stopped);
  });

  it('restarts from stopped, back to starting', () => {
    const stopped = run([
      { type: 'handshake', handshake: HANDSHAKE },
      { type: 'health-ok' },
      { type: 'exited', code: 1, signal: null },
    ]);

    expect(nextState(stopped, { type: 'retry' })).toEqual(INITIAL_STATE);
  });

  it('times out while starting or waiting for health, but not once ready', () => {
    const timeout: StartupEvent = { type: 'timeout', afterMs: 30000 };
    expect(run([timeout])).toMatchObject({ phase: 'failed', reason: 'timeout' });
    expect(run([{ type: 'handshake', handshake: HANDSHAKE }, timeout])).toMatchObject({
      phase: 'failed',
      reason: 'timeout',
    });
    expect(
      run([{ type: 'handshake', handshake: HANDSHAKE }, { type: 'health-ok' }, timeout]).phase,
    ).toBe('ready');
  });

  it('keeps the first failure: the exit caused by killing a timed-out backend changes nothing', () => {
    const failed = run([{ type: 'timeout', afterMs: 10 }, { type: 'exited', code: null, signal: 'SIGKILL' }]);

    expect(failed).toMatchObject({ phase: 'failed', reason: 'timeout' });
  });

  it('ignores events that do not apply to the current phase', () => {
    expect(run([{ type: 'health-ok' }])).toBe(INITIAL_STATE);
    const waiting = run([{ type: 'handshake', handshake: HANDSHAKE }]);
    expect(nextState(waiting, { type: 'handshake', handshake: { ...HANDSHAKE, port: 1 } })).toBe(waiting);
  });

  it('retries only from failed or stopped, back to starting', () => {
    expect(nextState(INITIAL_STATE, { type: 'retry' })).toBe(INITIAL_STATE);
    expect(run([{ type: 'timeout', afterMs: 1 }, { type: 'retry' }])).toEqual(INITIAL_STATE);
  });

  it('never exposes the token to the renderer', () => {
    const ready = run([{ type: 'handshake', handshake: HANDSHAKE }, { type: 'health-ok' }]);

    expect(publicState(ready)).toEqual({ phase: 'ready' });
    expect(JSON.stringify(publicState(ready))).not.toContain('secret');
    expect(publicState(run([{ type: 'timeout', afterMs: 1 }]))).toEqual({ phase: 'failed', reason: 'timeout' });
  });
});
