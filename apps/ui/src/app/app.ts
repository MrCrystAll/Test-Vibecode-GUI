// SPDX-License-Identifier: Apache-2.0
import { ChangeDetectionStrategy, Component } from '@angular/core';
import { Shell } from './core/layout/shell/shell';

@Component({
  selector: 'app-root',
  imports: [Shell],
  template: '<app-shell />',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {}
