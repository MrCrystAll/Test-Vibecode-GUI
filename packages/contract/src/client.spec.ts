// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';

import { createApiClient } from './client';

function recordingFetch(body: unknown, status = 200) {
  const requests: Request[] = [];
  const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    requests.push(input instanceof Request ? input : new Request(input, init));
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  return { fetch, requests };
}

describe('createApiClient', () => {
  it('calls the typed route on the base URL with the bearer token', async () => {
    const { fetch, requests } = recordingFetch({ status: 'ok' });
    const client = createApiClient({ baseUrl: 'http://127.0.0.1:5000', getToken: () => 't0k', fetch });

    const { data } = await client.GET('/api/health');

    expect(data).toEqual({ status: 'ok' });
    expect(requests[0]?.url).toBe('http://127.0.0.1:5000/api/health');
    expect(requests[0]?.headers.get('Authorization')).toBe('Bearer t0k');
  });

  it('reads the token on every request and omits the header without one', async () => {
    const { fetch, requests } = recordingFetch({ app_version: '0.1.0', api_version: '0.1.0' });
    let token: string | null = null;
    const client = createApiClient({ baseUrl: 'http://127.0.0.1:5000', getToken: () => token, fetch });

    await client.GET('/api/version');
    token = 'new';
    await client.GET('/api/version');

    expect(requests[0]?.headers.has('Authorization')).toBe(false);
    expect(requests[1]?.headers.get('Authorization')).toBe('Bearer new');
  });

  it('returns typed error bodies with the HTTP status', async () => {
    const body = { error: { code: 'unauthorized', message: 'Unauthorized', details: null } };
    const { fetch } = recordingFetch(body, 401);
    const client = createApiClient({ baseUrl: 'http://127.0.0.1:5000', getToken: () => 'bad', fetch });

    const { error, response } = await client.GET('/api/health');

    expect(response.status).toBe(401);
    expect(error).toEqual(body);
  });
});
