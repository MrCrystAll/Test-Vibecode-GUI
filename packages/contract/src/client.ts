// SPDX-License-Identifier: Apache-2.0
// The one hand-written HTTP client for the backend (ADR-0006): openapi-fetch typed by the generated schema,
// plus a middleware that sends the per-launch bearer token on every request.
import createClient, { type Client, type Middleware } from 'openapi-fetch';

import type { paths } from './generated/schema';

export type ApiClient = Client<paths>;

export interface ApiClientOptions {
  /** Backend origin, e.g. `http://127.0.0.1:51234`. Routes in the schema already start with `/api`. */
  baseUrl: string;
  /** Called for every request, so a backend restart with a new token needs no new client. */
  getToken: () => string | null;
  /** Injected in tests; defaults to the global `fetch`. */
  fetch?: typeof globalThis.fetch;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const client = createClient<paths>({
    baseUrl: options.baseUrl,
    ...(options.fetch ? { fetch: options.fetch } : {}),
  });
  client.use(bearerAuth(options.getToken));
  return client;
}

function bearerAuth(getToken: () => string | null): Middleware {
  return {
    onRequest({ request }) {
      const token = getToken();
      if (token) {
        request.headers.set('Authorization', `Bearer ${token}`);
      }
      return request;
    },
  };
}
