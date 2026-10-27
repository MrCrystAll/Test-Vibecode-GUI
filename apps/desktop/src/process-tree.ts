// SPDX-License-Identifier: Apache-2.0
// Stopping the backend means stopping its whole process tree. On Windows `uv run` starts
// uv -> venv launcher -> python, and killing only uv leaves python serving (QA finding on TC-23/TC-24).
import { execFile } from 'node:child_process';

export interface KillPlan {
  command: string;
  args: string[];
}

/**
 * How to kill the tree rooted at `pid` (the process we spawned). On POSIX the backend is spawned
 * `detached`, so it leads its own process group and `-pid` addresses the whole group.
 */
export function killPlan(platform: NodeJS.Platform, pid: number): KillPlan | { signalGroup: number } {
  if (platform === 'win32') {
    return { command: 'taskkill', args: ['/PID', String(pid), '/T', '/F'] };
  }
  return { signalGroup: -pid };
}

export async function killTree(pid: number, platform: NodeJS.Platform = process.platform): Promise<void> {
  const plan = killPlan(platform, pid);
  if ('signalGroup' in plan) {
    try {
      process.kill(plan.signalGroup, 'SIGKILL');
    } catch {
      // Already gone.
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
