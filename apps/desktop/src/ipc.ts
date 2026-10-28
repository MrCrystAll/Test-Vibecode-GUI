// SPDX-License-Identifier: Apache-2.0
// IPC channel names between main and preload. The sandboxed preload cannot require local files,
// so preload.ts repeats these strings; ipc.spec.ts checks the two lists stay identical.
export const IPC = {
  getBackendConnection: 'studio:get-backend-connection',
  getStartupState: 'studio:get-startup-state',
  startupState: 'studio:startup-state',
  retryBackend: 'studio:retry-backend',
  quit: 'studio:quit',
} as const;

/** What `window.studio.getBackendConnection()` resolves to (ADR-0006 shape). */
export interface BackendConnection {
  baseUrl: string;
  wsUrl: string;
  token: string;
}
