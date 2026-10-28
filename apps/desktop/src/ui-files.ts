// SPDX-License-Identifier: Apache-2.0
// Maps studio://app/<path> to a file of the built Angular app. Pure, so path traversal is tested.
import path from 'node:path';

export const UI_SCHEME = 'studio';
export const UI_HOST = 'app';
/** The renderer's origin; the backend must allow it (STUDIO_BACKEND_ALLOWED_ORIGINS, TC-19). */
export const UI_ORIGIN = `${UI_SCHEME}://${UI_HOST}`;

/**
 * The file to serve for `requestUrl`, or null when it must not be served. Paths without a file
 * extension are client-side routes (e.g. /status) and get index.html.
 */
export function resolveUiFile(uiRoot: string, requestUrl: string): string | null {
  let url: URL;
  try {
    url = new URL(requestUrl);
  } catch {
    return null;
  }
  if (url.protocol !== `${UI_SCHEME}:` || url.host !== UI_HOST) {
    return null;
  }
  let relative: string;
  try {
    relative = decodeURIComponent(url.pathname).replace(/^\/+/, '');
  } catch {
    return null;
  }
  if (relative.includes('\\') || relative.includes('\0')) {
    return null; // never in a real UI URL; a separator on Windows only, so refuse it everywhere
  }
  if (relative === '' || path.extname(relative) === '') {
    relative = 'index.html';
  }
  const root = path.resolve(uiRoot);
  const file = path.resolve(root, relative);
  return file.startsWith(root + path.sep) ? file : null;
}
