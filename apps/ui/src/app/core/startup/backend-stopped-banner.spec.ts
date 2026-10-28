// SPDX-License-Identifier: Apache-2.0
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { BackendStoppedBanner } from './backend-stopped-banner';
import { Startup } from './startup';

describe('BackendStoppedBanner', () => {
  it('says the backend stopped, and Restart asks the shell for a new one', () => {
    const startup = { phase: signal('stopped'), retry: vi.fn() };
    TestBed.configureTestingModule({
      imports: [BackendStoppedBanner],
      providers: [{ provide: Startup, useValue: startup }],
    });
    const fixture = TestBed.createComponent(BackendStoppedBanner);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('[data-testid="backend-stopped"]')?.textContent).toContain(
      'The backend stopped unexpectedly',
    );
    element.querySelector<HTMLButtonElement>('[data-testid="backend-stopped-restart"]')?.click();

    expect(startup.retry).toHaveBeenCalledOnce();
  });
});
