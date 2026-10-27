// SPDX-License-Identifier: Apache-2.0
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Shell } from './core/layout/shell/shell';
import { Startup } from './core/startup/startup';
import { StartupScreen } from './core/startup/startup-screen';

@Component({
  selector: 'app-root',
  imports: [Shell, StartupScreen],
  template: `
    @if (startup.phase() === 'ready') {
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
