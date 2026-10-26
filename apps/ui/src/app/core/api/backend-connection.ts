// SPDX-License-Identifier: Apache-2.0
// Where the backend is and how to authenticate, learned at runtime, never hard-coded (ADR-0006, TC-22 AC2).
import { InjectionToken } from '@angular/core';

export interface BackendConnection {
  /** Backend origin, e.g. `http://127.0.0.1:51234`. */
  baseUrl: string;
  /** Per-launch bearer token; null while the backend runs without auth (before TC-19). */
  token: string | null;
}

/** What Electron's preload script exposes through `contextBridge` (TC-23). */
export interface StudioBridge {
  getBackendConnection(): Promise<{ baseUrl: string; wsUrl: string; token: string }>;
}

declare global {
  interface Window {
    studio?: StudioBridge;
  }
}

/** Resolves the connection once at start-up. Rejects when no backend is configured. */
export type BackendConnectionSource = () => Promise<BackendConnection>;

/** Public path of the git-ignored dev config used when the UI runs in a plain browser (`ng serve`). */
export const DEV_CONNECTION_URL = 'dev-connection.json';

export const BACKEND_CONNECTION_SOURCE = new InjectionToken<BackendConnectionSource>(
  'BACKEND_CONNECTION_SOURCE',
  { providedIn: 'root', factory: () => () => defaultConnection(window) },
);

/** Electron's preload bridge when present, otherwise the browser dev config. */
export async function defaultConnection(win: Window): Promise<BackendConnection> {
  if (win.studio) {
    const { baseUrl, token } = await win.studio.getBackendConnection();
    return { baseUrl, token };
  }
  return readDevConnection(win.fetch.bind(win));
}

/**
 * Reads `dev-connection.json` from the dev server (a static asset, not a backend route; this is the only
 * `fetch` the UI is allowed, see eslint.config.js). Copy `public/dev-connection.example.json` to create it.
 */
export async function readDevConnection(
  fetchAsset: typeof globalThis.fetch,
): Promise<BackendConnection> {
  const response = await fetchAsset(DEV_CONNECTION_URL, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`${DEV_CONNECTION_URL}: HTTP ${response.status}`);
  }
  const value: unknown = await response.json();
  if (!isDevConnection(value)) {
    throw new Error(`${DEV_CONNECTION_URL}: expected {"baseUrl": string, "token": string | null}`);
  }
  return { baseUrl: value.baseUrl, token: value.token ?? null };
}

function isDevConnection(value: unknown): value is { baseUrl: string; token?: string | null } {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  const token = record['token'];
  return (
    typeof record['baseUrl'] === 'string' &&
    (token === undefined || token === null || typeof token === 'string')
  );
}
