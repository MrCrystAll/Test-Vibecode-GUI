// SPDX-License-Identifier: Apache-2.0
// Starts the backend, reads its handshake, waits for health and feeds the lifecycle state machine; stops it
// gracefully, then by force (TC-24). No business logic: the backend owns everything; this only supervises it.
import { type ChildProcess, spawn } from 'node:child_process';
import type { Writable } from 'node:stream';
import { createInterface } from 'node:readline';

import { parseHandshake } from './handshake';
import { waitForHealth } from './health';
import { removePidFile, writePidFile } from './pid-file';
import { killTree, waitForExit } from './process-tree';
import { DEFAULT_GRACEFUL_MS, stopBackend } from './shutdown';
import { INITIAL_STATE, type StartupEvent, type StartupState, nextState } from './startup';

export interface BackendOptions {
  command: readonly [string, ...string[]];
  cwd: string;
  /** Extra environment, e.g. STUDIO_BACKEND_ALLOWED_ORIGINS for the renderer's origin. */
  env: Readonly<Record<string, string>>;
  startupTimeoutMs: number;
  /** Receives the backend's stderr and any stdout after the handshake (`<userData>/logs/backend.log`). */
  backendLog: Writable;
  log: (message: string) => void;
  /** `<userData>/backend.pid` (see pid-file.ts), or null to keep none (tests). */
  pidFile: string | null;
  /** How long a stop waits for the graceful shutdown before killing (default 5 s). */
  gracefulMs?: number;
}

export class BackendSupervisor {
  private state: StartupState = INITIAL_STATE;
  private child: ChildProcess | null = null;
  private timer: NodeJS.Timeout | null = null;
  private readonly listeners = new Set<(state: StartupState) => void>();

  constructor(private readonly options: BackendOptions) {}

  get current(): StartupState {
    return this.state;
  }

  onChange(listener: (state: StartupState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  start(): void {
    const [command, ...args] = this.options.command;
    const startedAt = Date.now();
    this.options.log(`backend starting: ${this.options.command.join(' ')}`);
    const child = spawn(command, args, {
      cwd: this.options.cwd,
      // The backend stops gracefully when its stdin closes: on stop, or when this process dies (TC-24).
      env: { ...process.env, ...this.options.env, STUDIO_BACKEND_SHUTDOWN_ON_STDIN_EOF: '1' },
      stdio: ['pipe', 'pipe', 'pipe'],
      // POSIX: own process group, so the whole tree can be killed at once (see process-tree.ts).
      detached: process.platform !== 'win32',
      windowsHide: true,
    });
    this.child = child;
    child.stdin?.on('error', () => undefined); // EPIPE once the backend is gone: nothing to do
    this.recordPids(child, null);

    child.on('error', (error) => this.dispatch(child, { type: 'spawn-error', detail: error.message }));
    child.on('exit', (code, signal) => {
      this.options.log(`backend exited: code=${code ?? 'null'} signal=${signal ?? 'null'}`);
      this.dispatch(child, { type: 'exited', code, signal });
    });
    child.stderr?.pipe(this.options.backendLog, { end: false });

    if (!child.stdout) {
      throw new Error('backend stdout is not piped'); // cannot happen with stdio 'pipe'
    }
    let first = true;
    createInterface({ input: child.stdout }).on('line', (line) => {
      if (!first) {
        this.options.backendLog.write(`${line}\n`);
        return;
      }
      first = false;
      const result = parseHandshake(line);
      if (!result.ok) {
        this.dispatch(child, { type: 'bad-handshake', detail: result.error });
        return;
      }
      const { port, pid } = result.handshake;
      this.options.log(`backend started pid=${pid} port=${port}`); // never the token
      this.recordPids(child, pid);
      this.dispatch(child, { type: 'handshake', handshake: result.handshake });
      void this.awaitHealth(child, port, startedAt + this.options.startupTimeoutMs);
    });

    this.timer = setTimeout(
      () => this.dispatch(child, { type: 'timeout', afterMs: this.options.startupTimeoutMs }),
      this.options.startupTimeoutMs,
    );
  }

  /**
   * Stops the backend: closes its stdin (graceful shutdown), then kills the whole tree if it is still running after
   * `gracefulMs`, then checks the serving PID is gone. Safe to call at any time.
   */
  async stop(): Promise<void> {
    // Capture everything before the first await: the state may change while stopping. Clearing `this.child` first
    // means the exit this causes is not reported as a crash.
    const child = this.child;
    const servingPid = this.servingPid();
    this.child = null;
    this.clearTimer();
    const spawnedPid = child && isRunning(child) ? (child.pid ?? null) : null;
    const outcome = await stopBackend(
      { spawnedPid, servingPid },
      {
        closeStdin: () => child?.stdin?.end(),
        waitForExit: (pids, timeoutMs) => waitForExit(pids, timeoutMs),
        killTree: (pid) => killTree(pid),
      },
      this.options.gracefulMs ?? DEFAULT_GRACEFUL_MS,
    );
    if (spawnedPid !== null || servingPid !== null) {
      this.options.log(`backend stop: ${outcome} (spawned=${spawnedPid ?? '-'} serving=${servingPid ?? '-'})`);
    }
    if (outcome !== 'survived' && this.options.pidFile) {
      removePidFile(this.options.pidFile);
    }
  }

  /** Starts a new backend after a startup failure or a crash: a new process, so a new port and token. */
  async retry(): Promise<void> {
    if (this.state.phase !== 'failed' && this.state.phase !== 'stopped') {
      return;
    }
    await this.stop();
    this.setState(nextState(this.state, { type: 'retry' }));
    this.start();
  }

  private async awaitHealth(child: ChildProcess, port: number, deadline: number): Promise<void> {
    const healthy = await waitForHealth({
      baseUrl: `http://127.0.0.1:${port}`,
      deadline,
      cancelled: () => this.child !== child || this.state.phase !== 'waiting-health',
    });
    if (healthy) {
      this.dispatch(child, { type: 'health-ok' });
    }
  }

  private dispatch(child: ChildProcess, event: StartupEvent): void {
    if (child !== this.child) {
      return; // an event from a previous attempt (after retry or stop)
    }
    const next = nextState(this.state, event);
    if (next === this.state) {
      return;
    }
    if (next.phase === 'ready' || next.phase === 'failed') {
      this.clearTimer();
    }
    if (next.phase === 'failed' || next.phase === 'stopped') {
      this.options.log(
        next.phase === 'failed'
          ? `backend startup failed: ${next.reason}: ${next.detail}`
          : `backend stopped unexpectedly: ${next.detail}`,
      );
      // Kill whatever this attempt left running (after a crash of uv, python may still serve). `this.child` stays
      // set, so this attempt's late events still reach the state machine, which ignores them from now on.
      const pidFile = this.options.pidFile;
      void killProcesses(child, this.servingPid()).then(() => pidFile && removePidFile(pidFile));
    }
    this.setState(next);
  }

  private servingPid(): number | null {
    const state = this.state;
    return state.phase === 'waiting-health' || state.phase === 'ready' ? state.handshake.pid : null;
  }

  private recordPids(child: ChildProcess, servingPid: number | null): void {
    if (this.options.pidFile && child.pid !== undefined) {
      writePidFile(this.options.pidFile, { spawnedPid: child.pid, servingPid });
    }
  }

  private setState(state: StartupState): void {
    this.state = state;
    for (const listener of this.listeners) {
      listener(state);
    }
  }

  private clearTimer(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}

/** Kills the spawned tree, then the serving python by its handshake PID (it may sit outside that tree). */
async function killProcesses(child: ChildProcess | null, servingPid: number | null): Promise<void> {
  if (child?.pid !== undefined && isRunning(child)) {
    await killTree(child.pid);
  }
  if (servingPid !== null) {
    await killTree(servingPid);
  }
}

function isRunning(child: ChildProcess): boolean {
  return child.exitCode === null && child.signalCode === null;
}
