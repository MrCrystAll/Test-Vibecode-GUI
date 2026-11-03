// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';

import {
  e2eHookAnswer,
  isTrustedSender,
  selectDirectory,
  type DialogResult,
  type IpcSender,
  type SelectDirectoryDeps,
} from './select-directory';

const trusted = { webContentsId: 1, uiOrigin: 'studio://app' };
const studioWindow: IpcSender = { webContentsId: 1, isMainFrame: true, frameUrl: 'studio://app/projects' };

function deps(overrides: Partial<SelectDirectoryDeps> = {}, answer?: DialogResult) {
  const calls: string[] = [];
  const all: SelectDirectoryDeps = {
    trusted,
    hookAnswer: undefined,
    showDialog: async () => {
      calls.push('dialog');
      return answer ?? { canceled: false, filePaths: ['C:\\Users\\me\\studio é ws'] };
    },
    ...overrides,
  };
  return { all, calls };
}

describe('selectDirectory', () => {
  it('returns the folder chosen in the native dialog', async () => {
    const { all, calls } = deps();

    expect(await selectDirectory(studioWindow, all)).toBe('C:\\Users\\me\\studio é ws');
    expect(calls).toEqual(['dialog']);
  });

  it('returns null when the user cancels', async () => {
    expect(await selectDirectory(studioWindow, deps({}, { canceled: true, filePaths: [] }).all)).toBeNull();
    expect(await selectDirectory(studioWindow, deps({}, { canceled: false, filePaths: [] }).all)).toBeNull();
  });

  it.each<[string, IpcSender]>([
    ['another window', { ...studioWindow, webContentsId: 2 }],
    ['a sub-frame of the studio window', { ...studioWindow, isMainFrame: false }],
    ['the studio window navigated elsewhere', { ...studioWindow, frameUrl: 'https://example.com/' }],
    ['a frame that is gone', { ...studioWindow, frameUrl: '' }],
  ])('rejects a call from %s without opening the dialog', async (_name, sender) => {
    const { all, calls } = deps();

    await expect(selectDirectory(sender, all)).rejects.toThrow(/refused/);
    expect(calls).toEqual([]);
  });

  it('rejects every call while there is no window', async () => {
    await expect(selectDirectory(studioWindow, deps({ trusted: null }).all)).rejects.toThrow(/refused/);
  });

  it('answers with the e2e hook instead of opening the dialog', async () => {
    const chosen = deps({ hookAnswer: '/tmp/ws' });
    const cancelled = deps({ hookAnswer: null });

    expect(await selectDirectory(studioWindow, chosen.all)).toBe('/tmp/ws');
    expect(await selectDirectory(studioWindow, cancelled.all)).toBeNull();
    expect([...chosen.calls, ...cancelled.calls]).toEqual([]);
  });

  it('still rejects a foreign sender when the e2e hook is on', async () => {
    await expect(
      selectDirectory({ ...studioWindow, webContentsId: 9 }, deps({ hookAnswer: '/tmp/ws' }).all),
    ).rejects.toThrow(/refused/);
  });
});

describe('isTrustedSender', () => {
  it('accepts the live-reload UI origin when the shell runs with STUDIO_UI_URL', () => {
    const dev = { webContentsId: 1, uiOrigin: 'http://localhost:4200' };

    expect(isTrustedSender({ ...studioWindow, frameUrl: 'http://localhost:4200/x' }, dev)).toBe(true);
    expect(isTrustedSender({ ...studioWindow, frameUrl: 'http://localhost:4201/x' }, dev)).toBe(false);
  });
});

describe('e2eHookAnswer', () => {
  const on = { STUDIO_E2E: '1', STUDIO_E2E_SELECT_DIRECTORY: '/tmp/ws' };

  it('is honoured in test mode (STUDIO_E2E=1, unpackaged app)', () => {
    expect(e2eHookAnswer(on, false)).toBe('/tmp/ws');
    expect(e2eHookAnswer({ ...on, STUDIO_E2E_SELECT_DIRECTORY: '__cancel__' }, false)).toBeNull();
  });

  it('is ignored in a normal launch', () => {
    expect(e2eHookAnswer({ STUDIO_E2E_SELECT_DIRECTORY: '/tmp/ws' }, false)).toBeUndefined();
    expect(e2eHookAnswer({ ...on, STUDIO_E2E: 'true' }, false)).toBeUndefined();
  });

  it('is ignored by a packaged app, even with STUDIO_E2E=1', () => {
    expect(e2eHookAnswer(on, true)).toBeUndefined();
  });

  it('is off when the variable is unset or empty', () => {
    expect(e2eHookAnswer({ STUDIO_E2E: '1' }, false)).toBeUndefined();
    expect(e2eHookAnswer({ STUDIO_E2E: '1', STUDIO_E2E_SELECT_DIRECTORY: '' }, false)).toBeUndefined();
  });
});
