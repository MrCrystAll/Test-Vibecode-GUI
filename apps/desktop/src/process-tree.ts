// SPDX-License-Identifier: Apache-2.0
// Stopping the backend means stopping its whole process tree. On Windows `uv run` starts
// uv -> venv launcher -> python, and killing only uv leaves python serving (QA finding on TC-23/TC-24).
import { execFile } from 'node:child_process';
import { readFile } from 'node:fs/promises';

export interface KillPlan {
  command: string;
  args: string[];
}

/**
 * How to kill the tree rooted at `pid`. On POSIX the backend is spawned `detached`, so the PID we spawned leads its
 * own process group and `-pid` addresses the whole group. Other PIDs (the serving python from the handshake, an
 * orphan from the PID file) are not group leaders, so the process itself is signalled too.
 */
export function killPlan(platform: NodeJS.Platform, pid: number): KillPlan | { signals: number[] } {
  if (platform === 'win32') {
    return { command: 'taskkill', args: ['/PID', String(pid), '/T', '/F'] };
  }
  return { signals: [-pid, pid] };
}

export async function killTree(pid: number, platform: NodeJS.Platform = process.platform): Promise<void> {
  const plan = killPlan(platform, pid);
  if ('signals' in plan) {
    for (const target of plan.signals) {
      try {
        process.kill(target, 'SIGKILL');
      } catch {
        // No such group (not a leader) or already gone.
      }
    }
    return;
  }
  await new Promise<void>((resolve) => {
    // taskkill exits non-zero when the process is already gone; that is fine here.
    execFile(plan.command, plan.args, { windowsHide: true }, () => resolve());
  });
}

/** True while a process with this PID exists (signal 0 only checks). */
export function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === 'EPERM';
  }
}

export interface WaitForExitOptions {
  isAlive?: (pid: number) => boolean;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
  intervalMs?: number;
}

/** True once none of `pids` exists any more; false if one is still alive after `timeoutMs`. */
export async function waitForExit(
  pids: readonly number[],
  timeoutMs: number,
  options: WaitForExitOptions = {},
): Promise<boolean> {
  const alive = options.isAlive ?? isAlive;
  const now = options.now ?? Date.now;
  const sleep = options.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const deadline = now() + timeoutMs;
  while (pids.some(alive)) {
    if (now() >= deadline) {
      return false;
    }
    await sleep(options.intervalMs ?? 50);
  }
  return true;
}

/** Command line of a running process, or null when it is gone or cannot be read. */
export async function commandLineOf(pid: number, platform: NodeJS.Platform = process.platform): Promise<string | null> {
  if (platform !== 'win32') {
    try {
      return (await readFile(`/proc/${pid}/cmdline`, 'utf8')).split('\0').join(' ').trim() || null;
    } catch {
      return null;
    }
  }
  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-Command', `(Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}').CommandLine`],
      { windowsHide: true, timeout: 10_000 },
      (error, stdout) => resolve(error ? null : stdout.trim() || null),
    );
  });
}
