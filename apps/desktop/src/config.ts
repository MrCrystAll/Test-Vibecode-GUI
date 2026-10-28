// SPDX-License-Identifier: Apache-2.0
// Launch configuration from argv + environment, resolved once before `app.whenReady()`. Pure, so it is tested.
import path from 'node:path';

export interface LaunchConfig {
  /** `--user-data-dir=<path>` or STUDIO_USER_DATA_DIR: isolates profiles, e.g. one per e2e test (TC-29). */
  userDataDir: string | null;
  /** Live `ng serve` URL (STUDIO_UI_URL) instead of the built UI served on studio://app. */
  uiUrl: string | null;
  /** Backend command: STUDIO_BACKEND_CMD as a JSON array (dev/test override), else `uv run` (ADR-0005 dev mode). */
  backendCommand: readonly [string, ...string[]];
  /** Folder the backend command runs in: the repository root in dev mode. */
  backendCwd: string;
  /** How long the backend has to print its handshake and answer /api/health (STUDIO_BACKEND_STARTUP_TIMEOUT_MS). */
  startupTimeoutMs: number;
  /** Chromium --no-sandbox, only with STUDIO_E2E_NO_SANDBOX=1 (Linux CI containers). */
  noSandbox: boolean;
}

export const DEFAULT_BACKEND_COMMAND = ['uv', 'run', '--package', 'studio-backend', 'studio-backend'] as const;
export const DEFAULT_STARTUP_TIMEOUT_MS = 30_000;

type Env = Readonly<Record<string, string | undefined>>;

export function parseLaunchConfig(argv: readonly string[], env: Env, repoRoot: string): LaunchConfig {
  return {
    userDataDir: argValue(argv, '--user-data-dir') ?? nonEmpty(env['STUDIO_USER_DATA_DIR']),
    uiUrl: nonEmpty(env['STUDIO_UI_URL']),
    backendCommand: parseCommand(env['STUDIO_BACKEND_CMD']),
    backendCwd: repoRoot,
    startupTimeoutMs: parseTimeout(env['STUDIO_BACKEND_STARTUP_TIMEOUT_MS']),
    noSandbox: env['STUDIO_E2E_NO_SANDBOX'] === '1',
  };
}

/** apps/desktop/dist/main.js -> the repository root. */
export function repoRootFrom(distDir: string): string {
  return path.resolve(distDir, '..', '..', '..');
}

function argValue(argv: readonly string[], name: string): string | null {
  for (const arg of argv) {
    if (arg.startsWith(`${name}=`)) {
      return nonEmpty(arg.slice(name.length + 1));
    }
  }
  return null;
}

function nonEmpty(value: string | undefined): string | null {
  return value && value.trim() ? value : null;
}

function parseCommand(raw: string | undefined): readonly [string, ...string[]] {
  if (!nonEmpty(raw)) {
    return DEFAULT_BACKEND_COMMAND;
  }
  const value: unknown = JSON.parse(raw as string);
  if (
    !Array.isArray(value) ||
    value.length === 0 ||
    !value.every((part): part is string => typeof part === 'string' && part.length > 0)
  ) {
    throw new Error('STUDIO_BACKEND_CMD must be a JSON array of non-empty strings');
  }
  return value as [string, ...string[]];
}

function parseTimeout(raw: string | undefined): number {
  if (!nonEmpty(raw)) {
    return DEFAULT_STARTUP_TIMEOUT_MS;
  }
  const value = Number(raw);
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error('STUDIO_BACKEND_STARTUP_TIMEOUT_MS must be a positive integer');
  }
  return value;
}
