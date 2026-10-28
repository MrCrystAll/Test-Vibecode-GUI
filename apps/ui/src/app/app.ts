// SPDX-License-Identifier: Apache-2.0
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Shell } from './core/layout/shell/shell';
import { Startup } from './core/startup/startup';
import { BackendStoppedBanner } from './core/startup/backend-stopped-banner';
import { StartupScreen } from './core/startup/startup-screen';

@Component({
  selector: 'app-root',
  imports: [Shell, StartupScreen, BackendStoppedBanner],
  template: `
    @if (startup.phase() === 'ready' || startup.phase() === 'stopped') {
      @if (startup.phase() === 'stopped') {
        <app-backend-stopped-banner />
      }
      <app-shell />
    } @else {
      <app-startup-screen />
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  protected readonly startup = inject(Startup);
}
