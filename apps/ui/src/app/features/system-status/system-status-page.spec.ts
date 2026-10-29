// SPDX-License-Identifier: Apache-2.0
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ApiClient } from '@studio/contract';

import { BackendApi } from '../../core/api/backend-api';
import { SystemStatusPage } from './system-status-page';

function healthyClient(): ApiClient {
  const get = vi.fn(async (path: string) =>
    path === '/api/health'
      ? { data: { status: 'ok' }, response: { status: 200 } }
      : { data: { app_version: '0.1.2', api_version: '0.1.0' }, response: { status: 200 } },
  );
  return { GET: get } as unknown as ApiClient;
}

async function render(client: ApiClient | null): Promise<HTMLElement> {
  TestBed.configureTestingModule({
    imports: [SystemStatusPage],
    providers: [{ provide: BackendApi, useValue: { client: signal(client).asReadonly() } }],
  });
  const fixture = TestBed.createComponent(SystemStatusPage);
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('SystemStatusPage', () => {
  it('shows a healthy backend and its versions', async () => {
    const element = await render(healthyClient());
    const health = element.querySelector('[data-testid="status-health"]');

    expect(health?.getAttribute('data-state')).toBe('healthy');
    expect(health?.textContent).toContain('Healthy');
    expect(element.querySelector('[data-testid="status-version"]')?.textContent).toContain(
      'App 0.1.2, API 0.1.0',
    );
  });

  it('shows unreachable when there is no backend connection', async () => {
    const element = await render(null);
    const health = element.querySelector('[data-testid="status-health"]');

    expect(health?.getAttribute('data-state')).toBe('unreachable');
    expect(health?.textContent).toContain('Unreachable');
    expect(element.querySelector('[data-testid="status-version"]')?.textContent).toContain(
      'Unknown',
    );
  });

  it('starts in the loading state', () => {
    TestBed.configureTestingModule({
      imports: [SystemStatusPage],
      providers: [
        {
          provide: BackendApi,
          useValue: { client: signal({ GET: () => new Promise(() => undefined) }).asReadonly() },
        },
      ],
    });
    const fixture = TestBed.createComponent(SystemStatusPage);
    fixture.detectChanges();
    const health = (fixture.nativeElement as HTMLElement).querySelector(
      '[data-testid="status-health"]',
    );

    expect(health?.getAttribute('data-state')).toBe('loading');
    expect(health?.textContent).toContain('Checking…');
  });
});
