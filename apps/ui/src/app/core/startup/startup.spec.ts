// SPDX-License-Identifier: Apache-2.0
import { TestBed } from '@angular/core/testing';

import { BackendApi } from '../api/backend-api';
import { STUDIO_BRIDGE, type ShellStartupState, type StudioBridge } from '../api/backend-connection';
import { Startup } from './startup';

/** A fake preload bridge whose startup state the test drives. */
function fakeBridge(initial: ShellStartupState) {
  let listener: ((state: ShellStartupState) => void) | null = null;
  const bridge: StudioBridge = {
    getBackendConnection: vi.fn(),
    getStartupState: vi.fn(async () => initial),
    onStartupState: (l) => {
      listener = l;
      return () => (listener = null);
    },
    retryBackend: vi.fn(async () => undefined),
    quit: vi.fn(async () => undefined),
  };
  return { bridge, emit: (state: ShellStartupState) => listener?.(state) };
}

function setup(bridge: StudioBridge | null) {
  const api = { connect: vi.fn(async () => undefined) };
  TestBed.configureTestingModule({
    providers: [
      { provide: STUDIO_BRIDGE, useValue: bridge },
      { provide: BackendApi, useValue: api },
    ],
  });
  return { startup: TestBed.inject(Startup), api };
}

const settle = () => new Promise((resolve) => setTimeout(resolve));

describe('Startup', () => {
  it('in a plain browser, connects with the dev config and is ready', async () => {
    const { startup, api } = setup(null);

    await startup.init();

    expect(api.connect).toHaveBeenCalledOnce();
    expect(startup.phase()).toBe('ready');
  });

  it('in Electron, stays on the splash until the shell reports ready, then connects once', async () => {
    const { bridge, emit } = fakeBridge({ phase: 'starting' });
    const { startup, api } = setup(bridge);

    await startup.init();
    await settle();
    expect(startup.phase()).toBe('starting');

    emit({ phase: 'waiting-health' });
    await settle();
    expect(startup.phase()).toBe('starting');

    emit({ phase: 'ready' });
    emit({ phase: 'ready' });
    await settle();
    expect(startup.phase()).toBe('ready');
    expect(api.connect).toHaveBeenCalledOnce();
  });

  it('shows the failure reason, and Retry asks the shell to start again', async () => {
    const { bridge, emit } = fakeBridge({ phase: 'failed', reason: 'timeout' });
    const { startup } = setup(bridge);

    await startup.init();
    await settle();
    expect(startup.phase()).toBe('failed');
    expect(startup.reason()).toBe('timeout');

    startup.retry();
    expect(startup.phase()).toBe('starting');
    expect(bridge.retryBackend).toHaveBeenCalledOnce();

    emit({ phase: 'failed', reason: 'exited' });
    expect(startup.reason()).toBe('exited');
  });

  it('Quit asks the shell to quit', async () => {
    const { bridge } = fakeBridge({ phase: 'failed', reason: 'spawn-error' });
    const { startup } = setup(bridge);

    startup.quit();

    expect(bridge.quit).toHaveBeenCalledOnce();
  });
});
