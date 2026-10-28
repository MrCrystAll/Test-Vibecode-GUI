// SPDX-License-Identifier: Apache-2.0
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { Startup } from './startup';

/** Shown above the app when the backend died after start-up (TC-24 AC2): Restart starts a new one. */
@Component({
  selector: 'app-backend-stopped-banner',
  templateUrl: './backend-stopped-banner.html',
  styleUrl: './backend-stopped-banner.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BackendStoppedBanner {
  protected readonly startup = inject(Startup);
}
