// SPDX-License-Identifier: Apache-2.0
// A deliberately broken "backend" for the e2e startup-failure tests (TC-29, test plan T-23-2 / T-23-4).
// Plain Node, no dependencies. Used through STUDIO_BACKEND_CMD:
//   ["<node>", ".../fake-backend.cjs", "--mode", "<mode>", "--pid-file", "<file>"]
//
// Modes (each writes its own pid to --pid-file first, so a test can check it was killed afterwards):
//   exit        exits with code 3 at once
//   hang        prints nothing and stays alive (the shell must time out)
//   noise       prints a line that is not JSON, then stays alive
//   wrong-json  prints a JSON line that is not the handshake, then stays alive
'use strict';

const fs = require('node:fs');

function argument(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

const mode = argument('--mode');
const pidFile = argument('--pid-file');
if (pidFile) {
  fs.writeFileSync(pidFile, String(process.pid));
}

function stayAlive() {
  setInterval(() => undefined, 60_000);
}

switch (mode) {
  case 'exit':
    process.exit(3);
    break;
  case 'hang':
    stayAlive();
    break;
  case 'noise':
    process.stdout.write('this is not a handshake\n');
    stayAlive();
    break;
  case 'wrong-json':
    process.stdout.write('{"event":"starting"}\n');
    stayAlive();
    break;
  default:
    process.stderr.write(`fake-backend: unknown --mode ${String(mode)}\n`);
    process.exit(2);
}
