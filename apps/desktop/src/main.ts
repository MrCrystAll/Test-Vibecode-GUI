// SPDX-License-Identifier: Apache-2.0
// Electron main process (TC-23, TC-24): one window, one backend child process, one instance, nothing else.
// Business logic lives in the backend; the UI (Angular) shows the splash and startup errors.
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { BrowserWindow, app, ipcMain, net, protocol } from 'electron';

import { BackendSupervisor } from './backend';
import { parseLaunchConfig, repoRootFrom } from './config';
import { IPC, type BackendConnection } from './ipc';
import { openLogs } from './logs';
import { cleanUpOrphans, pidFilePath } from './pid-file';
import { commandLineOf, isAlive, killTree } from './process-tree';
import { publicState, type StartupState } from './startup';
import { UI_ORIGIN, UI_SCHEME, resolveUiFile } from './ui-files';

const repoRoot = repoRootFrom(__dirname);
const config = parseLaunchConfig(process.argv, process.env, repoRoot);
const uiRoot = path.join(repoRoot, 'apps', 'ui', 'dist', 'ui', 'browser');
const uiUrl = config.uiUrl ?? `${UI_ORIGIN}/`;
// Node's URL gives custom schemes an opaque 'null' origin, so the built UI's origin is spelled out.
const uiOrigin = config.uiUrl ? new URL(config.uiUrl).origin : UI_ORIGIN;

// --- before `ready` ------------------------------------------------------------------------------
if (config.userDataDir) {
  app.setPath('userData', path.resolve(config.userDataDir));
}
// One instance per profile (TC-24 AC3). Taken after --user-data-dir is applied, so e2e tests with their own
// profiles never collide. A second launch hands over to the first one, which focuses its window.
const isPrimaryInstance = app.requestSingleInstanceLock();
if (!isPrimaryInstance) {
  app.exit(0); // exits once this tick ends: nothing below starts a window or a backend (see the `ready` guard)
}
if (config.noSandbox) {
  app.commandLine.appendSwitch('no-sandbox');
}
protocol.registerSchemesAsPrivileged([
  {
    scheme: UI_SCHEME,
    privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true },
  },
]);

const logs = openLogs(app.getPath('userData'));
const pidFile = pidFilePath(app.getPath('userData'));
if (isPrimaryInstance) {
  logs.log(`app starting: userData=${app.getPath('userData')} ui=${uiUrl}`);
}

const backend = new BackendSupervisor({
  command: config.backendCommand,
  cwd: config.backendCwd,
  env: { STUDIO_BACKEND_ALLOWED_ORIGINS: uiOrigin },
  startupTimeoutMs: config.startupTimeoutMs,
  backendLog: logs.backend,
  log: logs.log,
  pidFile,
});

// --- IPC (the preload's typed API) -----------------------------------------------------------------
function connectionOf(state: StartupState): BackendConnection | null {
  if (state.phase !== 'ready') {
    return null;
  }
  const { port, token } = state.handshake;
  return { baseUrl: `http://127.0.0.1:${port}`, wsUrl: `ws://127.0.0.1:${port}/ws`, token };
}

ipcMain.handle(IPC.getStartupState, () => publicState(backend.current));
ipcMain.handle(IPC.getBackendConnection, () => {
  const connection = connectionOf(backend.current);
  if (!connection) {
    throw new Error(`backend not ready (${backend.current.phase})`);
  }
  return connection;
});
ipcMain.handle(IPC.retryBackend, () => backend.retry());
ipcMain.handle(IPC.quit, () => app.quit());

// --- window ----------------------------------------------------------------------------------------
function createWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  // The window only ever shows the studio UI: no pop-ups, no navigation elsewhere.
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(`${uiOrigin}/`)) {
      event.preventDefault();
    }
  });
  void window.loadURL(uiUrl);
  return window;
}

let mainWindow: BrowserWindow | null = null;

app.on('second-instance', () => {
  logs.log('second launch: focusing the existing window');
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    mainWindow.show();
    mainWindow.focus();
  }
});

app.on('window-all-closed', () => app.quit());

// Quit = stop the backend's whole tree first, then exit. `app.exit` (not a second `app.quit`) because a
// quit requested while Electron is still unwinding the cancelled one is silently dropped, which hung the
// app when there was nothing left to stop.
let quitting = false;
app.on('before-quit', (event) => {
  event.preventDefault();
  if (quitting) {
    return;
  }
  quitting = true;
  void backend.stop().finally(() => {
    logs.log('backend stopped, exiting');
    logs.close();
    app.exit(0);
  });
});

void app.whenReady().then(() => {
  if (!isPrimaryInstance) {
    return;
  }
  protocol.handle(UI_SCHEME, (request) => {
    const file = resolveUiFile(uiRoot, request.url);
    return file ? net.fetch(pathToFileURL(file).toString()) : new Response('Not found', { status: 404 });
  });
  const window = createWindow();
  mainWindow = window;
  backend.onChange((state) => {
    if (!window.isDestroyed()) {
      window.webContents.send(IPC.startupState, publicState(state));
    }
  });
  // A backend left by a run that was killed (TC-24 AC4), recorded in the PID file. Usually it is already gone:
  // its stdin closed when that run died.
  void cleanUpOrphans(pidFile, { isAlive, commandLineOf, killTree, log: logs.log })
    .catch((error: unknown) => logs.log(`orphan check failed: ${String(error)}`))
    .finally(() => backend.start());
});
