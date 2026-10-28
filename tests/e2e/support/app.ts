// SPDX-License-Identifier: Apache-2.0
// Launch the real desktop app through its public surface (command line + environment) and observe it only
// through the UI, the log files under its user-data folder and the operating system. Nothing from apps/ or
// packages/ is imported (test strategy §2.2).
import { _electron as electron, type ElectronApplication, type Page, type TestInfo } from '@playwright/test';
import { spawnSync, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';

export const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const DESKTOP_DIR = path.join(REPO_ROOT, 'apps', 'desktop');
const UI_INDEX = path.join(REPO_ROOT, 'apps', 'ui', 'dist', 'ui', 'browser', 'index.html');
const DESKTOP_MAIN = path.join(DESKTOP_DIR, 'dist', 'main.js');

// The `electron` package exports the path of its binary (its types describe the in-app API instead).
// eslint-disable-next-line @typescript-eslint/no-require-imports
const electronBinary: string = require('electron');

export interface LaunchOptions {
  /** Extra environment variables for the app (e.g. STUDIO_BACKEND_CMD, STUDIO_BACKEND_STARTUP_TIMEOUT_MS). */
  env?: Record<string, string>;
}

/** What the shell writes to `main.log` once the backend is up: `backend started pid=<n> port=<m>`. */
export interface BackendInfo {
  pid: number;
  port: number;
}

export class StudioApp {
  private tracing = true;
  /** Taken at launch: Playwright refuses to hand it out once the app has closed. */
  private readonly electronProcess: ChildProcess;

  private constructor(
    readonly electronApp: ElectronApplication,
    readonly window: Page,
    readonly userData: string,
  ) {
    this.electronProcess = electronApp.process();
  }

  /** Starts the app with a fresh, empty user-data folder whose path has a space and a non-ASCII character. */
  static async launch(options: LaunchOptions = {}): Promise<StudioApp> {
    for (const required of [DESKTOP_MAIN, UI_INDEX]) {
      if (!fs.existsSync(required)) {
        throw new Error(`${required} is missing: run \`pnpm build\` first (the UI and the desktop shell)`);
      }
    }
    const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'studio e2é '));
    const env: Record<string, string> = {};
    for (const [key, value] of Object.entries(process.env)) {
      if (value !== undefined) {
        env[key] = value;
      }
    }
    Object.assign(env, options.env ?? {});
    const electronApp = await electron.launch({
      executablePath: electronBinary,
      args: [DESKTOP_DIR, `--user-data-dir=${userData}`],
      cwd: REPO_ROOT,
      env,
    });
    await electronApp.context().tracing.start({ screenshots: true, snapshots: true });
    const window = await electronApp.firstWindow();
    return new StudioApp(electronApp, window, userData);
  }

  get logsDir(): string {
    return path.join(this.userData, 'logs');
  }

  /** The text of `main.log` or `backend.log`; empty while the file does not exist yet. */
  readLog(name: 'main.log' | 'backend.log'): string {
    try {
      return fs.readFileSync(path.join(this.logsDir, name), 'utf-8');
    } catch {
      return '';
    }
  }

  /** The serving python's pid and port, once `main.log` says the backend started. */
  backendInfo(): BackendInfo | null {
    const match = /backend started pid=(\d+) port=(\d+)/.exec(this.readLog('main.log'));
    return match ? { pid: Number(match[1]), port: Number(match[2]) } : null;
  }

  /** Quit the way a user does from the menu: `app.quit()`. Resolves when the Electron process has ended. */
  async quit(): Promise<void> {
    const closed = this.electronApp.waitForEvent('close');
    await this.electronApp.evaluate(({ app }) => app.quit()).catch(() => undefined); // the process exits mid-call
    await closed;
  }

  /** Close the last window, which also quits the app (the title-bar ✕). */
  async closeWindow(): Promise<void> {
    const closed = this.electronApp.waitForEvent('close');
    await this.window.close();
    await closed;
  }

  /** End of test: keep evidence if the test failed, then make sure nothing of the app is left. */
  async dispose(testInfo: TestInfo): Promise<void> {
    const failed = testInfo.status !== testInfo.expectedStatus;
    if (failed) {
      await this.attachEvidence(testInfo);
    }
    await this.stopTracing(failed ? testInfo.outputPath(`trace-${path.basename(this.userData)}.zip`) : null, testInfo);
    await this.killElectron();
    const info = this.backendInfo();
    if (info && isProcessAlive(info.pid)) {
      try {
        process.kill(info.pid);
      } catch {
        // already gone
      }
    }
    if (failed) {
      console.log(`kept the user-data folder of the failed test: ${this.userData}`);
    } else {
      // Windows may still hold a log file for a moment after the process ended.
      fs.rmSync(this.userData, { recursive: true, force: true, maxRetries: 30, retryDelay: 300 });
    }
  }

  /** Kill the Electron main process if it is still running and wait until it has really exited. */
  private async killElectron(): Promise<void> {
    const proc = this.electronProcess;
    if (proc.exitCode !== null || proc.signalCode !== null) {
      return;
    }
    const exited = new Promise<void>((resolve) => proc.once('exit', () => resolve()));
    if (process.platform === 'win32' && proc.pid !== undefined) {
      // Chromium's helper processes (GPU, renderer, utility) keep the profile folder open for a while after the
      // main process dies, so end the whole tree.
      spawnSync('taskkill', ['/PID', String(proc.pid), '/T', '/F'], { stdio: 'ignore' });
    } else {
      // Same on POSIX: Chromium's zygote/renderer/GPU children would outlive a bare SIGKILL of the main process and
      // keep Playwright's pipes open (the worker then hangs at teardown). Collect the tree first, then kill it.
      const tree = proc.pid === undefined ? [] : descendantPids(proc.pid);
      proc.kill('SIGKILL');
      for (const pid of tree) {
        try {
          process.kill(pid, 'SIGKILL');
        } catch {
          // already gone
        }
      }
    }
    await Promise.race([exited, new Promise<void>((resolve) => setTimeout(resolve, 10_000))]);
  }

  private async attachEvidence(testInfo: TestInfo): Promise<void> {
    for (const name of ['main.log', 'backend.log'] as const) {
      const body = this.readLog(name);
      if (body) {
        await testInfo.attach(name, { body, contentType: 'text/plain' });
      }
    }
    try {
      await testInfo.attach('window.png', {
        body: await this.window.screenshot({ timeout: 5_000 }),
        contentType: 'image/png',
      });
    } catch {
      // the window may already be closed
    }
  }

  private async stopTracing(keepAs: string | null, testInfo: TestInfo): Promise<void> {
    if (!this.tracing) {
      return;
    }
    this.tracing = false;
    try {
      await this.electronApp.context().tracing.stop(keepAs ? { path: keepAs } : {});
      if (keepAs) {
        await testInfo.attach('trace.zip', { path: keepAs, contentType: 'application/zip' });
      }
    } catch {
      // the app was closed by the test: the trace cannot be written
    }
  }
}

/** All descendants of a process (POSIX, via `ps`); empty when `ps` is unavailable. */
function descendantPids(root: number): number[] {
  const out = spawnSync('ps', ['-e', '-o', 'pid=,ppid='], { encoding: 'utf-8' }).stdout ?? '';
  const children = new Map<number, number[]>();
  for (const line of out.split('\n')) {
    const [pid, ppid] = line.trim().split(/\s+/).map(Number);
    if (pid !== undefined && ppid !== undefined && !Number.isNaN(pid) && !Number.isNaN(ppid)) {
      children.set(ppid, [...(children.get(ppid) ?? []), pid]);
    }
  }
  const found: number[] = [];
  const queue = [root];
  while (queue.length > 0) {
    for (const child of children.get(queue.pop() as number) ?? []) {
      found.push(child);
      queue.push(child);
    }
  }
  return found;
}

/** True while a process with this pid exists (permission errors still mean it exists). */
export function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === 'EPERM';
  }
}

/** True while something accepts connections on 127.0.0.1:port. */
export function isPortOpen(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.connect({ host: '127.0.0.1', port });
    socket.once('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.once('error', () => resolve(false));
  });
}
