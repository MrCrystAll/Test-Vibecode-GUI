// SPDX-License-Identifier: Apache-2.0
// @ts-check
const eslint = require('@eslint/js');
const tseslint = require('typescript-eslint');

module.exports = tseslint.config(
  { ignores: ['dist/**'] },
  {
    files: ['**/*.ts'],
    extends: [eslint.configs.recommended, ...tseslint.configs.strict, ...tseslint.configs.stylistic],
  },
  {
    files: ['eslint.config.js'],
    languageOptions: { sourceType: 'commonjs', globals: { require: 'readonly', module: 'writable' } },
  },
);
