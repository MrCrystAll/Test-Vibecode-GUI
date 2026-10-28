// SPDX-License-Identifier: Apache-2.0
// A stand-in backend for backend.spec.ts: same handshake and /api/health as apps/backend, same stdin shutdown
// signal. `node fake-backend.cjs [ignore-stdin]`; GET /crash makes it exit with code 7.
'use strict';
const crypto = require('node:crypto');
const http = require('node:http');

const ignoreStdin = process.argv[2] === 'ignore-stdin';

const server = http.createServer((request, response) => {
  if (request.url === '/api/health') {
    response.end('{"status":"ok"}');
  } else if (request.url === '/crash') {
    response.end();
    process.exit(7);
  } else {
    response.statusCode = 404;
    response.end();
  }
});

server.listen(0, '127.0.0.1', () => {
  const handshake = {
    event: 'listening',
    port: server.address().port,
    token: crypto.randomBytes(16).toString('hex'),
    pid: process.pid,
  };
  process.stdout.write(`${JSON.stringify(handshake)}\n`);
});

process.stdin.resume();
if (!ignoreStdin && process.env.STUDIO_BACKEND_SHUTDOWN_ON_STDIN_EOF === '1') {
  process.stdin.on('end', () => server.close(() => process.exit(0)));
}
