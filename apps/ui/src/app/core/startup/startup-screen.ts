// SPDX-License-Identifier: Apache-2.0
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { Startup } from './startup';

/** Splash while the backend starts, or the startup error with Retry / Quit. */
@Component({
  selector: 'app-startup-screen',
  templateUrl: './startup-screen.html',
  styleUrl: './startup-screen.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StartupScreen {
  protected readonly startup = inject(Startup);
}
