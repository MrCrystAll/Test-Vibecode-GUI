// SPDX-License-Identifier: Apache-2.0
// @ts-check
const eslint = require('@eslint/js');
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');

module.exports = tseslint.config(
  {
    files: ['**/*.ts'],
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.strict,
      ...tseslint.configs.stylistic,
      ...angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
    rules: {
      // Angular components and directives are decorated classes that may legitimately be empty.
      '@typescript-eslint/no-extraneous-class': ['error', { allowWithDecorator: true }],
      '@angular-eslint/directive-selector': [
        'error',
        { type: 'attribute', prefix: 'app', style: 'camelCase' },
      ],
      '@angular-eslint/component-selector': [
        'error',
        { type: 'element', prefix: 'app', style: 'kebab-case' },
      ],
      // TC-22 AC4 / ADR-0006: the backend is reached only through the generated client in @studio/contract,
      // so hand-written HTTP or WebSocket calls fail lint.
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: 'Use the generated client (BackendApi), not fetch.' },
        { name: 'XMLHttpRequest', message: 'Use the generated client (BackendApi).' },
        { name: 'WebSocket', message: 'Use the @studio/contract WebSocket helpers (TC-20).' },
      ],
      'no-restricted-properties': [
        'error',
        { property: 'fetch', message: 'Use the generated client (BackendApi), not fetch.' },
      ],
      'no-restricted-imports': [
        'error',
        {
          paths: [
            { name: '@angular/common/http', message: 'Use the generated client (ADR-0006).' },
          ],
        },
      ],
    },
  },
  {
    // The one allowed fetch: the browser-only dev connection file, a static asset (not a backend route).
    files: ['src/app/core/api/backend-connection.ts'],
    rules: { 'no-restricted-properties': 'off' },
  },
  {
    files: ['**/*.html'],
    extends: [...angular.configs.templateRecommended, ...angular.configs.templateAccessibility],
    rules: {
      // i18n-ready (TC-21): every user-visible text node and text attribute in a template must be
      // marked for translation, so hard-coded copy fails lint. Custom message ids are not required.
      '@angular-eslint/template/i18n': [
        'error',
        {
          checkId: false,
          checkText: true,
          checkAttributes: true,
          requireDescription: false,
          requireMeaning: false,
          // Never shown to users: e2e test hooks (TC-29) and ARIA references to element ids.
          ignoreAttributes: ['data-testid', 'aria-labelledby', 'aria-describedby'],
        },
      ],
    },
  },
);
