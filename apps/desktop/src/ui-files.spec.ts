// SPDX-License-Identifier: Apache-2.0
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { resolveUiFile } from './ui-files';

const ROOT = path.resolve('/ui/browser');

describe('resolveUiFile', () => {
  it('serves files of the built app', () => {
    expect(resolveUiFile(ROOT, 'studio://app/main-ABC.js')).toBe(path.join(ROOT, 'main-ABC.js'));
    expect(resolveUiFile(ROOT, 'studio://app/media/logo.svg')).toBe(path.join(ROOT, 'media', 'logo.svg'));
  });

  it('serves index.html for the root and for client-side routes', () => {
    expect(resolveUiFile(ROOT, 'studio://app/')).toBe(path.join(ROOT, 'index.html'));
    expect(resolveUiFile(ROOT, 'studio://app/status')).toBe(path.join(ROOT, 'index.html'));
  });

  it('stays inside the root when the URL parser already normalised dot segments', () => {
    expect(resolveUiFile(ROOT, 'studio://app/../secret.txt')).toBe(path.join(ROOT, 'secret.txt'));
    expect(resolveUiFile(ROOT, 'studio://app/%2e%2e/secret.txt')).toBe(path.join(ROOT, 'secret.txt'));
  });

  it.each([
    'studio://app/..%2f..%2fsecret.txt',
    'studio://app/..%5c..%5csecret.txt',
    'studio://app/%E0%A4%A',
    'studio://other/main.js',
    'https://app/main.js',
    'not a url',
  ])('refuses %s', (url) => {
    expect(resolveUiFile(ROOT, url)).toBeNull();
  });
});
