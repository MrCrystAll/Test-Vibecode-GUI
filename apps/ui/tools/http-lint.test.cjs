// SPDX-License-Identifier: Apache-2.0
// Proves eslint.config.js rejects hand-written HTTP / WebSocket calls (TC-22 AC4, ADR-0006): the backend is
// reached only through the generated client. Run by `pnpm lint`.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { ESLint } = require('eslint');

const eslint = new ESLint({ cwd: path.join(__dirname, '..') });
const RULES = new Set(['no-restricted-globals', 'no-restricted-properties', 'no-restricted-imports']);

async function httpErrors(code, file = 'src/app/features/http-lint-fixture.ts') {
  const [result] = await eslint.lintText(code, { filePath: path.join(__dirname, '..', file) });
  return result.messages.filter((m) => RULES.has(m.ruleId));
}

test('global fetch fails lint', async () => {
  assert.notEqual((await httpErrors("export const r = fetch('/api/health');\n")).length, 0);
});

test('window.fetch fails lint', async () => {
  assert.notEqual((await httpErrors("export const r = window.fetch('/api/health');\n")).length, 0);
});

test('XMLHttpRequest and WebSocket fail lint', async () => {
  assert.notEqual((await httpErrors('export const x = new XMLHttpRequest();\n')).length, 0);
  assert.notEqual((await httpErrors("export const w = new WebSocket('ws://x');\n")).length, 0);
});

test("Angular's HttpClient fails lint", async () => {
  const code = "import { HttpClient } from '@angular/common/http';\nexport type H = HttpClient;\n";
  assert.notEqual((await httpErrors(code)).length, 0);
});

test('the generated client passes lint', async () => {
  const code =
    "import { createApiClient } from '@studio/contract';\n" +
    "export const c = createApiClient({ baseUrl: '', getToken: () => null });\n";
  assert.equal((await httpErrors(code)).length, 0);
});
