// SPDX-License-Identifier: Apache-2.0
// Proves the i18n lint rule (eslint.config.js) rejects hard-coded user-visible template text.
// Run with `node --test tools/i18n-lint.test.cjs` (part of `pnpm lint`).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { ESLint } = require('eslint');

const eslint = new ESLint({ cwd: path.join(__dirname, '..') });
const templatePath = path.join(__dirname, '..', 'src', 'app', 'i18n-lint-fixture.html');

async function i18nErrors(template) {
  const [result] = await eslint.lintText(template, { filePath: templatePath });
  return result.messages.filter((m) => m.ruleId === '@angular-eslint/template/i18n');
}

test('hard-coded text in a template fails lint', async () => {
  assert.notEqual((await i18nErrors('<p>Start training</p>\n')).length, 0);
});

test('hard-coded user-visible attribute fails lint', async () => {
  assert.notEqual((await i18nErrors('<input placeholder="Search runs" />\n')).length, 0);
});

test('text marked with i18n passes lint', async () => {
  assert.equal((await i18nErrors('<p i18n>Start training</p>\n')).length, 0);
  assert.equal(
    (await i18nErrors('<input placeholder="Search runs" i18n-placeholder />\n')).length,
    0,
  );
});
