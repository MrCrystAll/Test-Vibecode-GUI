// SPDX-License-Identifier: Apache-2.0
import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, signal } from '@angular/core';

/** Placeholder landing page until projects arrive (0.2.0). */
@Component({
  selector: 'app-home-page',
  imports: [DatePipe],
  templateUrl: './home-page.html',
  styleUrl: './home-page.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HomePage {
  protected readonly today = signal(new Date());
  protected readonly projectCount = signal(0);
}
