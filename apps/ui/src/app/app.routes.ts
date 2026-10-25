// SPDX-License-Identifier: Apache-2.0
import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    title: $localize`:@@route.home.title:Home · rlgym-learn studio`,
    loadComponent: () => import('./features/home/home-page').then((m) => m.HomePage),
  },
  { path: '**', redirectTo: '' },
];
