// SPDX-License-Identifier: Apache-2.0
// The backend's first stdout line (contract in apps/backend/README.md, TC-19):
//   {"event":"listening","port":12345,"token":"<per-launch token>","pid":4321}
// Unknown keys are ignored so the backend can add fields without breaking the shell.

export interface Handshake {
  port: number;
  token: string;
  /** PID of the Python process serving the API (not uv / the venv launcher in front of it). */
  pid: number;
}

export type HandshakeResult = { ok: true; handshake: Handshake } | { ok: false; error: string };

export function parseHandshake(line: string): HandshakeResult {
  let value: unknown;
  try {
    value = JSON.parse(line);
  } catch {
    return { ok: false, error: 'not JSON' };
  }
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return { ok: false, error: 'not a JSON object' };
  }
  const record = value as Record<string, unknown>;
  if (record['event'] !== 'listening') {
    return { ok: false, error: 'event is not "listening"' };
  }
  const { port, token, pid } = record;
  if (!isInteger(port) || port < 1 || port > 65535) {
    return { ok: false, error: 'port must be an integer in 1..65535' };
  }
  if (typeof token !== 'string' || token.length === 0) {
    return { ok: false, error: 'token must be a non-empty string' };
  }
  if (!isInteger(pid) || pid < 1) {
    return { ok: false, error: 'pid must be a positive integer' };
  }
  return { ok: true, handshake: { port, token, pid } };
}

function isInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value);
}
