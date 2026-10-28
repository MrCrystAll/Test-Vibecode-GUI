// SPDX-License-Identifier: Apache-2.0
// Polls GET /api/health until it answers 200 or the deadline passes. The liveness probe needs no token
// (TC-19), and the main process sends no Origin header, so the backend's origin check does not apply.

export interface WaitForHealthOptions {
  baseUrl: string;
  deadline: number;
  intervalMs?: number;
  fetch?: typeof globalThis.fetch;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
  /** Stops polling early, e.g. when the backend exited meanwhile. */
  cancelled?: () => boolean;
}

export async function waitForHealth(options: WaitForHealthOptions): Promise<boolean> {
  const fetchFn = options.fetch ?? globalThis.fetch;
  const now = options.now ?? Date.now;
  const sleep = options.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const interval = options.intervalMs ?? 200;
  while (now() < options.deadline && !options.cancelled?.()) {
    try {
      const response = await fetchFn(`${options.baseUrl}/api/health`, {
        signal: AbortSignal.timeout(Math.max(1, Math.min(2000, options.deadline - now()))),
      });
      if (response.ok) {
        return true;
      }
    } catch {
      // Not listening yet, or the request timed out: try again.
    }
    await sleep(interval);
  }
  return false;
}
