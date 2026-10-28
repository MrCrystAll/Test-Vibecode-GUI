// SPDX-License-Identifier: Apache-2.0
// @ts-check
const eslint = require('@eslint/js');
const tseslint = require('typescript-eslint');

module.exports = tseslint.config(
  { ignores: ['test-results/**', 'playwright-report/**'] },
  {
    files: ['**/*.ts'],
    extends: [eslint.configs.recommended, ...tseslint.configs.strict, ...tseslint.configs.stylistic],
    rules: {
      // No sleeps: wait for a condition (test strategy §1.5).
      'no-restricted-properties': [
        'error',
        { object: 'page', property: 'waitForTimeout', message: 'Wait for a condition, never a fixed time.' },
        { object: 'window', property: 'waitForTimeout', message: 'Wait for a condition, never a fixed time.' },
      ],
    },
  },
  {
    files: ['eslint.config.js'],
    languageOptions: { sourceType: 'commonjs', globals: { require: 'readonly', module: 'writable' } },
  },
);
