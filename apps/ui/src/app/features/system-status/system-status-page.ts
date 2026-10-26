// SPDX-License-Identifier: Apache-2.0
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import type { VersionResponse } from '@studio/contract';

import { BackendApi } from '../../core/api/backend-api';
import { type HealthState, checkSystemStatus } from './system-status';

/** "System status" screen: is the backend up, and which versions does it run. */
@Component({
  selector: 'app-system-status-page',
  templateUrl: './system-status-page.html',
  styleUrl: './system-status-page.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SystemStatusPage {
  private readonly api = inject(BackendApi);
  protected readonly health = signal<HealthState>('loading');
  protected readonly version = signal<VersionResponse | null>(null);

  constructor() {
    void this.refresh();
  }

  protected async refresh(): Promise<void> {
    this.health.set('loading');
    const status = await checkSystemStatus(this.api.client());
    this.health.set(status.health);
    this.version.set(status.version);
  }
}
