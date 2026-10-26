// SPDX-License-Identifier: Apache-2.0
import type { ApiClient } from '@studio/contract';

import { checkSystemStatus } from './system-status';

type Reply = { status: number; data?: unknown } | Error;

/** A mock of the generated client: only GET, answering per route. */
function mockClient(replies: Record<string, Reply>): ApiClient {
  const get = vi.fn(async (path: string) => {
    const reply = replies[path];
    if (!reply || reply instanceof Error) {
      throw reply ?? new Error(`unexpected ${path}`);
    }
    return { data: reply.data, error: undefined, response: { status: reply.status } };
  });
  return { GET: get } as unknown as ApiClient;
}

const VERSION = { app_version: '0.1.0', api_version: '0.1.0' };

describe('checkSystemStatus', () => {
  it('is healthy with versions when both routes answer', async () => {
    const client = mockClient({
      '/api/health': { status: 200, data: { status: 'ok' } },
      '/api/version': { status: 200, data: VERSION },
    });

    expect(await checkSystemStatus(client)).toEqual({ health: 'healthy', version: VERSION });
  });

  it('is unauthorised on a 401', async () => {
    const client = mockClient({
      '/api/health': { status: 401 },
      '/api/version': { status: 401 },
    });

    expect(await checkSystemStatus(client)).toEqual({ health: 'unauthorised', version: null });
  });

  it('is unreachable when the request fails', async () => {
    const client = mockClient({
      '/api/health': new TypeError('Failed to fetch'),
      '/api/version': new TypeError('Failed to fetch'),
    });

    expect(await checkSystemStatus(client)).toEqual({ health: 'unreachable', version: null });
  });

  it('is unreachable on an unexpected error status', async () => {
    const client = mockClient({
      '/api/health': { status: 500 },
      '/api/version': { status: 200, data: VERSION },
    });

    expect((await checkSystemStatus(client)).health).toBe('unreachable');
  });

  it('is unreachable without a client (no backend connection)', async () => {
    expect(await checkSystemStatus(null)).toEqual({ health: 'unreachable', version: null });
  });
});
