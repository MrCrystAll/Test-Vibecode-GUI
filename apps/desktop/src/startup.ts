// SPDX-License-Identifier: Apache-2.0
// Backend startup as a pure state machine (TC-23 AC6): the launcher feeds it events, the window shows its state.
//
//   starting --handshake--> waiting-health --health-ok--> ready
//      |                         |                          |
//      +--- exited / error / timeout / bad handshake -------+--> failed --retry--> starting
import type { Handshake } from './handshake';

export type FailureReason = 'spawn-error' | 'exited' | 'bad-handshake' | 'timeout';

export type StartupState =
  | { phase: 'starting' }
  | { phase: 'waiting-health'; handshake: Handshake }
  | { phase: 'ready'; handshake: Handshake }
  | { phase: 'failed'; reason: FailureReason; detail: string };

export type StartupEvent =
  | { type: 'handshake'; handshake: Handshake }
  | { type: 'bad-handshake'; detail: string }
  | { type: 'health-ok' }
  | { type: 'spawn-error'; detail: string }
  | { type: 'exited'; code: number | null; signal: string | null }
  | { type: 'timeout'; afterMs: number }
  | { type: 'retry' };

export const INITIAL_STATE: StartupState = { phase: 'starting' };

export function nextState(state: StartupState, event: StartupEvent): StartupState {
  switch (event.type) {
    case 'retry':
      return state.phase === 'failed' ? INITIAL_STATE : state;
    case 'handshake':
      return state.phase === 'starting' ? { phase: 'waiting-health', handshake: event.handshake } : state;
    case 'health-ok':
      return state.phase === 'waiting-health' ? { phase: 'ready', handshake: state.handshake } : state;
    case 'bad-handshake':
      return state.phase === 'starting' ? failed('bad-handshake', event.detail) : state;
    case 'spawn-error':
      return state.phase === 'failed' ? state : failed('spawn-error', event.detail);
    case 'exited':
      // An exit after a failure (e.g. the kill that follows a timeout) changes nothing.
      return state.phase === 'failed' ? state : failed('exited', describeExit(event.code, event.signal));
    case 'timeout':
      return state.phase === 'starting' || state.phase === 'waiting-health'
        ? failed('timeout', `backend not healthy after ${event.afterMs} ms`)
        : state;
  }
}

/** The part of the state the renderer may see: never the token. */
export interface PublicStartupState {
  phase: StartupState['phase'];
  reason?: FailureReason;
}

export function publicState(state: StartupState): PublicStartupState {
  return state.phase === 'failed' ? { phase: 'failed', reason: state.reason } : { phase: state.phase };
}

function failed(reason: FailureReason, detail: string): StartupState {
  return { phase: 'failed', reason, detail };
}

function describeExit(code: number | null, signal: string | null): string {
  return signal ? `backend exited on signal ${signal}` : `backend exited with code ${code ?? 'unknown'}`;
}
