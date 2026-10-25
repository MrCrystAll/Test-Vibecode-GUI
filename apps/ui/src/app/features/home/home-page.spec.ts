// SPDX-License-Identifier: Apache-2.0
import { TestBed } from '@angular/core/testing';
import { HomePage } from './home-page';

describe('HomePage', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [HomePage] }).compileComponents();
  });

  it('renders the source-locale (en-US) texts', async () => {
    const fixture = TestBed.createComponent(HomePage);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('h1')?.textContent).toContain('Welcome');
    expect(element.querySelector('.home-summary')?.textContent).toContain(
      'You have no projects yet.',
    );
  });

  it('formats the date through the locale-aware date pipe', async () => {
    const fixture = TestBed.createComponent(HomePage);
    fixture.componentRef.instance['today'].set(new Date(2026, 9, 25));
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('.home-date')?.textContent).toContain(
      'Sunday, October 25, 2026',
    );
  });
});
