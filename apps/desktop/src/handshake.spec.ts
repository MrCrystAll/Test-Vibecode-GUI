// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';

import { parseHandshake } from './handshake';

describe('parseHandshake', () => {
  it('reads port, token and pid from the TC-19 handshake line', () => {
    const line = '{"event":"listening","port":51234,"token":"abc_DEF-123","pid":4321}';

    expect(parseHandshake(line)).toEqual({
      ok: true,
      handshake: { port: 51234, token: 'abc_DEF-123', pid: 4321 },
    });
  });

  it('ignores keys it does not know', () => {
    const line = '{"event":"listening","port":1,"token":"t","pid":2,"version":"9.9.9"}';

    expect(parseHandshake(line)).toEqual({ ok: true, handshake: { port: 1, token: 't', pid: 2 } });
  });

  it.each([
    ['', 'not JSON'],
    ['Traceback (most recent call last):', 'not JSON'],
    ['[1, 2]', 'not a JSON object'],
    ['null', 'not a JSON object'],
    ['{"event":"started","port":1,"token":"t","pid":2}', 'event is not "listening"'],
    ['{"event":"listening","port":0,"token":"t","pid":2}', 'port must be an integer in 1..65535'],
    ['{"event":"listening","port":70000,"token":"t","pid":2}', 'port must be an integer in 1..65535'],
    ['{"event":"listening","port":"80","token":"t","pid":2}', 'port must be an integer in 1..65535'],
    ['{"event":"listening","port":80.5,"token":"t","pid":2}', 'port must be an integer in 1..65535'],
    ['{"event":"listening","port":80,"token":"","pid":2}', 'token must be a non-empty string'],
    ['{"event":"listening","port":80,"pid":2}', 'token must be a non-empty string'],
    ['{"event":"listening","port":80,"token":"t"}', 'pid must be a positive integer'],
    ['{"event":"listening","port":80,"token":"t","pid":-1}', 'pid must be a positive integer'],
  ])('rejects %j: %s', (line, error) => {
    expect(parseHandshake(line)).toEqual({ ok: false, error });
  });
});
