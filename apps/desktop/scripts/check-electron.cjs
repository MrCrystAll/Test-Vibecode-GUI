#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// TC-48: fail early, with the fix in the message, when Electron's binary is missing or does not match the installed
// `electron` package. Since Electron 45 the package has no postinstall: the binary comes from its `install-electron`
// bin, which this package's own `postinstall` runs. This script mirrors that bin's `isInstalled()` check.
// Plain CommonJS on purpose: it runs before anything is built (`pnpm start`, tools/ci/run.py e2e).
'use strict';
const fs = require('node:fs');
const path = require('node:path');

const FIX = 'corepack pnpm --filter @studio/desktop run install-electron';

/**
 * @param {string} electronDir the installed `electron` package folder
 * @returns {{ ok: true, executable: string } | { ok: false, problem: string }}
 */
function checkElectronBinary(electronDir) {
  let version;
  try {
    version = JSON.parse(fs.readFileSync(path.join(electronDir, 'package.json'), 'utf8')).version;
  } catch {
    return { ok: false, problem: `the electron package is not installed (${electronDir})` };
  }
  const pathFile = path.join(electronDir, 'path.txt');
  if (!fs.existsSync(pathFile)) {
    return { ok: false, problem: `the Electron ${version} binary was never downloaded (no ${pathFile})` };
  }
  const executable = path.join(electronDir, 'dist', fs.readFileSync(pathFile, 'utf8').trim());
  if (!fs.existsSync(executable)) {
    return { ok: false, problem: `the Electron binary is missing: ${executable}` };
  }
  let distVersion = '';
  try {
    distVersion = fs.readFileSync(path.join(electronDir, 'dist', 'version'), 'utf8').trim().replace(/^v/, '');
  } catch {
    // reported just below
  }
  if (distVersion !== version) {
    return {
      ok: false,
      problem: `the downloaded Electron binary is ${distVersion || 'unknown'}, the electron package is ${version}`,
    };
  }
  return { ok: true, executable };
}

function main() {
  const electronDir = path.dirname(require.resolve('electron/package.json', { paths: [path.join(__dirname, '..')] }));
  const result = checkElectronBinary(electronDir);
  if (result.ok) {
    console.log(`Electron binary OK: ${result.executable}`);
    return 0;
  }
  console.error(`Electron check failed: ${result.problem}.\nFix: ${FIX}`);
  return 1;
}

module.exports = { checkElectronBinary, FIX };

if (require.main === module) {
  process.exitCode = main();
}
