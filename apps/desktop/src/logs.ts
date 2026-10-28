// SPDX-License-Identifier: Apache-2.0
// Log files under `<userData>/logs/` (TC-23 AC4): main.log for the shell, backend.log for the backend's output.
import fs from 'node:fs';
import path from 'node:path';

export interface Logs {
  dir: string;
  log: (message: string) => void;
  backend: fs.WriteStream;
  close: () => void;
}

export function openLogs(userDataDir: string): Logs {
  const dir = path.join(userDataDir, 'logs');
  fs.mkdirSync(dir, { recursive: true });
  const main = fs.createWriteStream(path.join(dir, 'main.log'), { flags: 'a' });
  const backend = fs.createWriteStream(path.join(dir, 'backend.log'), { flags: 'a' });
  return {
    dir,
    log: (message) => main.write(`${new Date().toISOString()} ${message}\n`),
    backend,
    close: () => {
      main.end();
      backend.end();
    },
  };
}
