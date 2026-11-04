// SPDX-License-Identifier: Apache-2.0
// scripts/check-electron.cjs (TC-48): the clear failure when the Electron binary is missing.
import fs from 'node:fs';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

type Result = { ok: true; executable: string } | { ok: false; problem: string };
const { checkElectronBinary, FIX } = createRequire(__filename)('../scripts/check-electron.cjs') as {
  checkElectronBinary: (dir: string) => Result;
  FIX: string;
};

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

/** A fake `electron` package folder, filled in step by step like install-electron does. */
function fakeElectron(steps: { pathTxt?: boolean; binary?: boolean; distVersion?: string } = {}): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'studio electron é '));
  dirs.push(dir);
  fs.writeFileSync(path.join(dir, 'package.json'), JSON.stringify({ name: 'electron', version: '45.0.0' }));
  if (steps.pathTxt) {
    fs.writeFileSync(path.join(dir, 'path.txt'), 'electron.exe');
  }
  if (steps.binary || steps.distVersion !== undefined) {
    fs.mkdirSync(path.join(dir, 'dist'));
  }
  if (steps.binary) {
    fs.writeFileSync(path.join(dir, 'dist', 'electron.exe'), '');
  }
  if (steps.distVersion !== undefined) {
    fs.writeFileSync(path.join(dir, 'dist', 'version'), steps.distVersion);
  }
  return dir;
}

describe('checkElectronBinary', () => {
  it('passes when the downloaded binary matches the package version', () => {
    const dir = fakeElectron({ pathTxt: true, binary: true, distVersion: 'v45.0.0' });

    expect(checkElectronBinary(dir)).toEqual({ ok: true, executable: path.join(dir, 'dist', 'electron.exe') });
  });

  it('fails when the binary was never downloaded (the TC-48 fresh-install case)', () => {
    const result = checkElectronBinary(fakeElectron());

    expect(result).toMatchObject({ ok: false, problem: expect.stringContaining('never downloaded') });
  });

  it('fails when path.txt points at a missing executable', () => {
    const result = checkElectronBinary(fakeElectron({ pathTxt: true, distVersion: '45.0.0' }));

    expect(result).toMatchObject({ ok: false, problem: expect.stringContaining('binary is missing') });
  });

  it('fails when the binary is from another Electron version', () => {
    const result = checkElectronBinary(fakeElectron({ pathTxt: true, binary: true, distVersion: 'v44.1.0' }));

    expect(result).toMatchObject({ ok: false, problem: expect.stringContaining('44.1.0') });
  });

  it('fails when the electron package itself is absent', () => {
    const dir = fakeElectron();
    fs.rmSync(path.join(dir, 'package.json'));

    expect(checkElectronBinary(dir)).toMatchObject({ ok: false, problem: expect.stringContaining('not installed') });
  });

  it('tells the user the one command that fixes it', () => {
    expect(FIX).toBe('corepack pnpm --filter @studio/desktop run install-electron');
  });
});
