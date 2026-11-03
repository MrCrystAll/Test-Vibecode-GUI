// SPDX-License-Identifier: Apache-2.0
// `window.studio.selectDirectory()` (TC-46): the native folder dialog, opened by the main process.
// The renderer only ever gets back the chosen path string, or null on cancel. Pure, so it is unit-tested;
// main.ts wires it to ipcMain with Electron's real dialog.

/** The e2e hook's value that means "the user cancelled". */
export const E2E_CANCEL = '__cancel__';

/** Who sent the IPC call: taken from the IpcMainInvokeEvent in main.ts. */
export interface IpcSender {
  /** `event.sender.id`: the webContents that sent the call. */
  webContentsId: number;
  /** `event.senderFrame` is the top frame of that webContents (false for iframes or a frame that is gone). */
  isMainFrame: boolean;
  /** `event.senderFrame.url`, empty when the frame is gone. */
  frameUrl: string;
}

/** The only sender allowed to open the dialog: the app's own window, showing the studio UI. */
export interface TrustedWindow {
  webContentsId: number;
  uiOrigin: string;
}

export interface DialogResult {
  canceled: boolean;
  filePaths: readonly string[];
}

export interface SelectDirectoryDeps {
  /** null while there is no window (e.g. it was closed): every call is then rejected. */
  trusted: TrustedWindow | null;
  /** What the e2e hook answers instead of the dialog; undefined when the hook is off (see `e2eHookAnswer`). */
  hookAnswer: string | null | undefined;
  /** Opens the native dialog (`dialog.showOpenDialog` with openDirectory + createDirectory). */
  showDialog: () => Promise<DialogResult>;
}

export function isTrustedSender(sender: IpcSender, trusted: TrustedWindow | null): boolean {
  if (!trusted || sender.webContentsId !== trusted.webContentsId || !sender.isMainFrame) {
    return false;
  }
  return originOf(sender.frameUrl) === trusted.uiOrigin;
}

/**
 * The e2e hook (AC4): `STUDIO_E2E_SELECT_DIRECTORY` is honoured only in test mode, i.e. `STUDIO_E2E=1` in an
 * unpackaged app. Returns undefined when the hook is off, null for `__cancel__`, else the path to answer.
 */
export function e2eHookAnswer(
  env: Readonly<Record<string, string | undefined>>,
  isPackaged: boolean,
): string | null | undefined {
  const value = env['STUDIO_E2E_SELECT_DIRECTORY'];
  if (isPackaged || env['STUDIO_E2E'] !== '1' || value === undefined || value === '') {
    return undefined;
  }
  return value === E2E_CANCEL ? null : value;
}

export async function selectDirectory(sender: IpcSender, deps: SelectDirectoryDeps): Promise<string | null> {
  if (!isTrustedSender(sender, deps.trusted)) {
    throw new Error('selectDirectory refused: the call does not come from the studio window');
  }
  if (deps.hookAnswer !== undefined) {
    return deps.hookAnswer;
  }
  const result = await deps.showDialog();
  const [chosen] = result.filePaths;
  return result.canceled || chosen === undefined ? null : chosen;
}

function originOf(url: string): string | null {
  try {
    // Node gives custom schemes an opaque 'null' origin (see main.ts), so build it from protocol + host.
    const parsed = new URL(url);
    return `${parsed.protocol}//${parsed.host}`;
  } catch {
    return null;
  }
}
