// SPDX-License-Identifier: Apache-2.0
// Electron lifecycle (test plan T-24-1 .. T-24-4): graceful and forced stop, backend crash + restart,
// single instance, no process left after quit / window close / main-process kill / orphan clean-up.
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

import { DESKTOP_DIR, REPO_ROOT, electronBinary, isProcessAlive, type StudioApp } from '../../support/app';
import { expect, expectGone, fakeBackendCommand, test } from '../../support/fixtures';

/** Wait for the real backend to be up and return its pid and port. */
async function runningBackend(studio: StudioApp): Promise<{ pid: number; port: number }> {
  await expect(studio.window.getByTestId('nav-status')).toBeVisible();
  await expect.poll(() => studio.backendInfo()).not.toBeNull();
  return studio.backendInfo() as { pid: number; port: number };
}

function killPid(pid: number): void {
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' });
  } else {
    process.kill(pid, 'SIGKILL');
  }
}

async function connection(studio: StudioApp): Promise<unknown> {
  return studio.window.evaluate(async () => {
    const bridge = (window as unknown as { studio: { getBackendConnection: () => Promise<unknown> } }).studio;
    return bridge.getBackendConnection();
  });
}

test('quit stops the backend gracefully', { tag: ['@TC-24', '@TC-24-AC1', '@TC-24-AC4'] }, async ({ launchApp }) => {
  const studio = await launchApp();
  const backend = await runningBackend(studio);
  await studio.quit();
  await expectGone(backend);
  expect(studio.readLog('main.log')).toContain('backend stop: graceful');
  expect(fs.existsSync(path.join(studio.userData, 'backend.pid'))).toBe(false);
});

test('closing the window leaves no backend', { tag: ['@TC-24', '@TC-24-AC4'] }, async ({ launchApp }) => {
  const studio = await launchApp();
  const backend = await runningBackend(studio);
  await studio.closeWindow();
  await expectGone(backend);
});

test('a backend that ignores the shutdown signal is force-killed with its children', {
  tag: ['@TC-24', '@TC-24-AC1'],
}, async ({ launchApp }) => {
  const pidFile = test.info().outputPath('stubborn.pid');
  const studio = await launchApp({ env: { STUDIO_BACKEND_CMD: fakeBackendCommand('stubborn', pidFile) } });
  await expect.poll(() => fs.existsSync(`${pidFile}.child`)).toBe(true);
  await expect.poll(() => studio.backendInfo()).not.toBeNull();
  const pid = Number(fs.readFileSync(pidFile, 'utf-8'));
  const childPid = Number(fs.readFileSync(`${pidFile}.child`, 'utf-8'));
  expect(isProcessAlive(pid)).toBe(true);
  expect(isProcessAlive(childPid)).toBe(true);

  await studio.quit();

  await expectGone({ pid });
  await expectGone({ pid: childPid });
  expect(studio.readLog('main.log')).toContain('backend stop: killed');
});

test('killing the backend shows the banner; Restart gives a new port and token and a healthy status', {
  tag: ['@TC-24', '@TC-24-AC2'],
}, async ({ launchApp }) => {
  const studio = await launchApp();
  const page = studio.window;
  const first = await runningBackend(studio);
  const before = JSON.stringify(await connection(studio));

  killPid(first.pid);

  await expect(page.getByTestId('backend-stopped')).toBeVisible();
  await page.getByTestId('backend-stopped-restart').click();
  await expect(page.getByTestId('backend-stopped')).toHaveCount(0);

  await expect.poll(() => studio.backendInfo()?.pid).not.toBe(first.pid);
  await page.getByTestId('nav-status').click();
  await expect(page.getByTestId('status-health')).toHaveAttribute('data-state', 'healthy');
  // A new backend means a new random port and a new per-launch token.
  expect(JSON.stringify(await connection(studio))).not.toBe(before);
  const second = studio.backendInfo();

  await studio.quit();
  if (second) {
    await expectGone(second);
  }
});

test('a second launch with the same profile exits and focuses the first window', {
  tag: ['@TC-24', '@TC-24-AC3'],
}, async ({ launchApp }) => {
  const studio = await launchApp();
  await runningBackend(studio);

  const second = spawn(electronBinary, [DESKTOP_DIR, `--user-data-dir=${studio.userData}`], {
    cwd: REPO_ROOT,
    env: { ...process.env, ...(process.platform === 'linux' ? { STUDIO_E2E_NO_SANDBOX: '1' } : {}) },
    stdio: 'ignore',
  });
  const exit = await new Promise<string>((resolve) =>
    second.once('exit', (code, signal) => resolve(`code=${String(code)} signal=${String(signal)}`)),
  );
  expect(exit).toBe('code=0 signal=null');
  await expect.poll(() => studio.readLog('main.log')).toContain('second launch: focusing the existing window');
  expect(studio.electronApp.windows()).toHaveLength(1);
  await expect(studio.window.getByTestId('nav-status')).toBeVisible();
});

test('after the Electron main process is killed, the next start leaves no backend running', {
  tag: ['@TC-24', '@TC-24-AC4'],
}, async ({ launchApp }) => {
  const first = await launchApp();
  const backend = await runningBackend(first);
  // Not electronApp.process().pid: on Windows that is a cmd.exe wrapper around the real main process.
  const mainPid = await first.electronApp.evaluate(() => process.pid);

  process.kill(mainPid, 'SIGKILL'); // the main process only: TerminateProcess on Windows, not the tree

  // Either the backend stopped by itself (its stdin closed with the shell) or it is still recorded in backend.pid.
  await expect.poll(() => fs.existsSync(path.join(first.userData, 'backend.pid'))).toBe(true);
  await expect.poll(() => isProcessAlive(mainPid), { timeout: 10_000 }).toBe(false);
  const stoppedAlone = await expect.poll(() => isProcessAlive(backend.pid), { timeout: 10_000 }).toBe(false).then(
    () => true,
    () => false,
  );
  test.info().annotations.push({ type: 'backend stopped by itself', description: String(stoppedAlone) });

  // The next start (same profile) must leave exactly one backend: the new one.
  const second = await launchApp({ userData: first.userData });
  await runningBackend(second);
  await expectGone(backend);
  await second.quit();
});

test('the next start kills an orphan recorded in backend.pid and leaves an unrelated process alone', {
  tag: ['@TC-24', '@TC-24-AC4'],
}, async ({ launchApp }) => {
  // Decoys: one whose command line looks like our backend (studio_backend), one that does not.
  const sleeper = 'setInterval(() => undefined, 60000)';
  const orphan = spawn(process.execPath, ['-e', sleeper, 'studio_backend'], { stdio: 'ignore' });
  const bystander = spawn(process.execPath, ['-e', sleeper, 'qa-bystander'], { stdio: 'ignore' });
  try {
    const first = await launchApp();
    await runningBackend(first);
    await first.quit();
    // Pretend the previous run was killed before it could clean up: its record points at the decoys.
    const record = { spawnedPid: orphan.pid, servingPid: bystander.pid };
    fs.writeFileSync(path.join(first.userData, 'backend.pid'), `${JSON.stringify(record)}\n`);

    const second = await launchApp({ userData: first.userData });
    await runningBackend(second);

    await expectGone({ pid: orphan.pid as number });
    expect(isProcessAlive(bystander.pid as number)).toBe(true);
    await second.quit();
  } finally {
    for (const decoy of [orphan, bystander]) {
      if (decoy.pid !== undefined && isProcessAlive(decoy.pid)) {
        killPid(decoy.pid);
      }
    }
  }
});
