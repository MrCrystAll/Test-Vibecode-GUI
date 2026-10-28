// SPDX-License-Identifier: Apache-2.0
// `<userData>/backend.pid` (TC-24 AC4): the backend's PIDs while it runs, so the next start can clean up if the
// shell was killed before it could stop the backend. Usually the backend has already stopped by itself (its stdin
// closed with the shell); this is the fallback.
import fs from 'node:fs';
import path from 'node:path';

export interface PidRecord {
  spawnedPid: number | null;
  servingPid: number | null;
}

/** PIDs get reused: only a process whose command line still looks like our backend is killed. */
export const BACKEND_COMMAND_LINE = /studio[-_]backend/i;

export function pidFilePath(userDataDir: string): string {
  return path.join(userDataDir, 'backend.pid');
}

export function writePidFile(file: string, record: PidRecord): void {
  fs.writeFileSync(file, `${JSON.stringify(record)}\n`, 'utf8');
}

export function removePidFile(file: string): void {
  fs.rmSync(file, { force: true });
}

export function readPidFile(file: string): PidRecord | null {
  let value: unknown;
  try {
    value = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
  if (typeof value !== 'object' || value === null) {
    return null;
  }
  const record = value as Record<string, unknown>;
  return { spawnedPid: positiveInt(record['spawnedPid']), servingPid: positiveInt(record['servingPid']) };
}

export interface CleanupEffects {
  isAlive: (pid: number) => boolean;
  commandLineOf: (pid: number) => Promise<string | null>;
  killTree: (pid: number) => Promise<void>;
  log: (message: string) => void;
}

/** Kills what a previous run left behind, if it is still our backend, then deletes the PID file. */
export async function cleanUpOrphans(file: string, effects: CleanupEffects): Promise<number[]> {
  const record = readPidFile(file);
  const killed: number[] = [];
  for (const pid of [record?.servingPid, record?.spawnedPid]) {
    if (pid == null || !effects.isAlive(pid)) {
      continue;
    }
    const commandLine = await effects.commandLineOf(pid);
    if (commandLine === null || !BACKEND_COMMAND_LINE.test(commandLine)) {
      effects.log(`orphan check: pid=${pid} is no longer a studio backend, left alone`);
      continue;
    }
    effects.log(`orphan check: killing leftover backend pid=${pid}`);
    await effects.killTree(pid);
    killed.push(pid);
  }
  removePidFile(file);
  return killed;
}

function positiveInt(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : null;
}
