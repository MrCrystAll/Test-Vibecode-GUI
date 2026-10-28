// SPDX-License-Identifier: Apache-2.0
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import type { StartupFailureReason } from '../api/backend-connection';
import { Startup, type StartupPhase } from './startup';
import { StartupScreen } from './startup-screen';

function render(phase: StartupPhase, reason: StartupFailureReason | null = null) {
  const startup = {
    phase: signal(phase),
    reason: signal(reason),
    retry: vi.fn(),
    quit: vi.fn(),
  };
  TestBed.configureTestingModule({
    imports: [StartupScreen],
    providers: [{ provide: Startup, useValue: startup }],
  });
  const fixture = TestBed.createComponent(StartupScreen);
  fixture.detectChanges();
  return { element: fixture.nativeElement as HTMLElement, startup };
}

const byTestId = (element: HTMLElement, id: string) =>
  element.querySelector<HTMLElement>(`[data-testid="${id}"]`);

describe('StartupScreen', () => {
  it('shows the splash while the backend starts', () => {
    const { element } = render('starting');

    expect(byTestId(element, 'splash')?.textContent).toContain('Starting the backend…');
    expect(byTestId(element, 'startup-error')).toBeNull();
  });

  it.each<[StartupFailureReason, string]>([
    ['timeout', 'did not become ready in time'],
    ['spawn-error', 'could not be launched'],
    ['bad-handshake', 'unexpected startup message'],
    ['exited', 'stopped unexpectedly'],
  ])('explains a %s failure', (reason, text) => {
    const { element } = render('failed', reason);

    expect(byTestId(element, 'startup-error')?.textContent).toContain('The backend could not start');
    expect(byTestId(element, 'startup-error-reason')?.textContent).toContain(text);
    expect(byTestId(element, 'splash')).toBeNull();
  });

  it('wires Retry and Quit', () => {
    const { element, startup } = render('failed', 'timeout');

    byTestId(element, 'startup-error-retry')?.click();
    byTestId(element, 'startup-error-quit')?.click();

    expect(startup.retry).toHaveBeenCalledOnce();
    expect(startup.quit).toHaveBeenCalledOnce();
  });
});
