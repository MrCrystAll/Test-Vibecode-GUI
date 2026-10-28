// SPDX-License-Identifier: Apache-2.0
// What the app shows before the backend is usable (TC-23 AC3): a splash while the desktop shell starts the
// backend, an error with Retry / Quit if it fails, then the app. If the backend dies later, the app stays on
// screen with a "backend stopped" banner, and Restart goes through the splash again: the new backend has a new
// port and token, so the client is rebuilt and the pages load afresh (TC-24 AC2). In a plain browser there is
// no shell, so the app connects with the dev config and shows itself straight away.
import {
  EnvironmentProviders,
  Injectable,
  inject,
  provideAppInitializer,
  signal,
} from '@angular/core';

import { BackendApi } from '../api/backend-api';
import {
  STUDIO_BRIDGE,
  type ShellStartupState,
  type StartupFailureReason,
} from '../api/backend-connection';

export type StartupPhase = 'starting' | 'ready' | 'failed' | 'stopped';

@Injectable({ providedIn: 'root' })
export class Startup {
  private readonly api = inject(BackendApi);
  private readonly bridge = inject(STUDIO_BRIDGE);
  private readonly phaseSignal = signal<StartupPhase>('starting');
  private readonly reasonSignal = signal<StartupFailureReason | null>(null);
  private connecting: Promise<void> | null = null;

  readonly phase = this.phaseSignal.asReadonly();
  readonly reason = this.reasonSignal.asReadonly();

  /** Run once at bootstrap. Never blocks on the backend in Electron: the splash must render meanwhile. */
  async init(): Promise<void> {
    if (!this.bridge) {
      await this.api.connect();
      this.phaseSignal.set('ready');
      return;
    }
    this.bridge.onStartupState((state) => void this.apply(state));
    void this.bridge.getStartupState().then((state) => this.apply(state));
  }

  /** Retry after a startup failure, or Restart after a crash. */
  retry(): void {
    this.reasonSignal.set(null);
    this.phaseSignal.set('starting');
    void this.bridge?.retryBackend();
  }

  quit(): void {
    void this.bridge?.quit();
  }

  private async apply(state: ShellStartupState): Promise<void> {
    if (state.phase === 'failed') {
      this.reasonSignal.set(state.reason ?? null);
      this.phaseSignal.set('failed');
      return;
    }
    if (state.phase === 'stopped') {
      this.phaseSignal.set('stopped');
      return;
    }
    if (state.phase !== 'ready') {
      this.phaseSignal.set('starting');
      return;
    }
    // The initial query and the change event can both report `ready`: connect once.
    this.connecting ??= this.api.connect().finally(() => (this.connecting = null));
    await this.connecting;
    this.reasonSignal.set(null);
    this.phaseSignal.set('ready');
  }
}

export function provideStartup(): EnvironmentProviders {
  return provideAppInitializer(() => inject(Startup).init());
}
