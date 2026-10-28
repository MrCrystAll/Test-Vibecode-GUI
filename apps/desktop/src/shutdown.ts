// SPDX-License-Identifier: Apache-2.0
// Stopping the backend (TC-24 AC1): ask first, then force. Pure sequencing; the effects are injected so it is tested.
//
//   1. close the backend's stdin, its documented shutdown signal (`--shutdown-on-stdin-eof`, apps/backend/README.md);
//   2. wait up to `gracefulMs` for the serving python and the spawned process to exit;
//   3. otherwise kill the spawned tree and the serving PID (taskkill /T /F on Windows, process group on Linux);
//   4. check that they are really gone.

export type StopOutcome = 'graceful' | 'killed' | 'survived';

export interface StopTargets {
  /** PID we spawned (uv in dev mode), or null when it already exited. */
  spawnedPid: number | null;
  /** PID from the handshake: the python serving the API, or null before the handshake. */
  servingPid: number | null;
}

export interface StopEffects {
  closeStdin: () => void;
  waitForExit: (pids: readonly number[], timeoutMs: number) => Promise<boolean>;
  killTree: (pid: number) => Promise<void>;
}

export const DEFAULT_GRACEFUL_MS = 5_000;
export const KILL_CHECK_MS = 3_000;

export async function stopBackend(
  targets: StopTargets,
  effects: StopEffects,
  gracefulMs: number = DEFAULT_GRACEFUL_MS,
): Promise<StopOutcome> {
  const pids = [targets.spawnedPid, targets.servingPid].filter((pid): pid is number => pid !== null);
  if (pids.length === 0) {
    return 'graceful';
  }
  // Only a backend that has sent its handshake is serving and listening for the signal; before that, kill at once.
  if (targets.servingPid !== null) {
    effects.closeStdin();
    if (await effects.waitForExit(pids, gracefulMs)) {
      return 'graceful';
    }
  }
  for (const pid of pids) {
    await effects.killTree(pid);
  }
  return (await effects.waitForExit(pids, KILL_CHECK_MS)) ? 'killed' : 'survived';
}
