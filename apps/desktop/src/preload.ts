// SPDX-License-Identifier: Apache-2.0
// The renderer's only door to the main process (TC-23 AC2): contextIsolation + sandbox, no Node APIs.
// Sandboxed preloads may require only 'electron', so the channel names are repeated here (see ipc.ts).
import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron';

const CHANNELS = {
  getBackendConnection: 'studio:get-backend-connection',
  getStartupState: 'studio:get-startup-state',
  startupState: 'studio:startup-state',
  retryBackend: 'studio:retry-backend',
  quit: 'studio:quit',
} as const;

interface PublicStartupState {
  phase: 'starting' | 'waiting-health' | 'ready' | 'failed';
  reason?: 'spawn-error' | 'exited' | 'bad-handshake' | 'timeout';
}

const studio = {
  /** Resolves once the backend is ready; rejects if startup failed. */
  getBackendConnection: (): Promise<{ baseUrl: string; wsUrl: string; token: string }> =>
    ipcRenderer.invoke(CHANNELS.getBackendConnection),
  getStartupState: (): Promise<PublicStartupState> => ipcRenderer.invoke(CHANNELS.getStartupState),
  /** Calls `listener` on every startup state change; returns an unsubscribe function. */
  onStartupState: (listener: (state: PublicStartupState) => void): (() => void) => {
    const handler = (_event: IpcRendererEvent, state: PublicStartupState) => listener(state);
    ipcRenderer.on(CHANNELS.startupState, handler);
    return () => ipcRenderer.removeListener(CHANNELS.startupState, handler);
  },
  retryBackend: (): Promise<void> => ipcRenderer.invoke(CHANNELS.retryBackend),
  quit: (): Promise<void> => ipcRenderer.invoke(CHANNELS.quit),
};

contextBridge.exposeInMainWorld('studio', studio);

export const PRELOAD_CHANNELS = CHANNELS; // for ipc.spec.ts only
