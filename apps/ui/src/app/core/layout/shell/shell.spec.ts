// SPDX-License-Identifier: Apache-2.0
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Shell } from './shell';

describe('Shell', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Shell],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('renders a header with the app name and a main area for routes', async () => {
    const fixture = TestBed.createComponent(Shell);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('header')?.textContent).toContain('rlgym-learn studio');
    expect(element.querySelector('main router-outlet')).not.toBeNull();
    expect(element.querySelector('nav a[href="/status"]')?.textContent).toContain('System status');
  });

  it('exposes stable test ids on the navigation links for e2e', async () => {
    const fixture = TestBed.createComponent(Shell);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('[data-testid="nav-home"]')?.getAttribute('href')).toBe('/');
    expect(element.querySelector('[data-testid="nav-status"]')?.getAttribute('href')).toBe('/status');
  });
});
