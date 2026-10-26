// SPDX-License-Identifier: Apache-2.0
import { TestBed } from '@angular/core/testing';

import { BackendApi } from './backend-api';
import {
  BACKEND_CONNECTION_SOURCE,
  type BackendConnectionSource,
  defaultConnection,
  readDevConnection,
} from './backend-connection';

function setup(source: BackendConnectionSource): BackendApi {
  TestBed.configureTestingModule({
    providers: [{ provide: BACKEND_CONNECTION_SOURCE, useValue: source }],
  });
  return TestBed.inject(BackendApi);
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

describe('BackendApi', () => {
  it('creates the client from the resolved connection', async () => {
    const api = setup(async () => ({ baseUrl: 'http://127.0.0.1:5000', token: 'abc' }));

    await api.connect();

    expect(api.client()).not.toBeNull();
  });

  it('leaves the client null when no connection can be resolved', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const api = setup(async () => {
      throw new Error('no backend');
    });

    await api.connect();

    expect(api.client()).toBeNull();
  });
});

describe('defaultConnection', () => {
  it('uses the Electron preload bridge when present', async () => {
    const studio = {
      getBackendConnection: async () => ({
        baseUrl: 'http://127.0.0.1:6000',
        wsUrl: 'ws://127.0.0.1:6000/ws',
        token: 'from-electron',
      }),
    };

    const connection = await defaultConnection({ studio } as unknown as Window);

    expect(connection).toEqual({ baseUrl: 'http://127.0.0.1:6000', token: 'from-electron' });
  });
});

describe('readDevConnection', () => {
  it('reads baseUrl and token from the dev config', async () => {
    const fetchAsset = vi.fn(async () => jsonResponse({ baseUrl: '', token: null }));

    expect(await readDevConnection(fetchAsset)).toEqual({ baseUrl: '', token: null });
    expect(fetchAsset).toHaveBeenCalledWith('dev-connection.json', { cache: 'no-store' });
  });

  it('rejects a missing file', async () => {
    const fetchAsset = vi.fn(async () => jsonResponse({}, 404));

    await expect(readDevConnection(fetchAsset)).rejects.toThrow('HTTP 404');
  });

  it('rejects a malformed file', async () => {
    const fetchAsset = vi.fn(async () => jsonResponse({ baseUrl: 42 }));

    await expect(readDevConnection(fetchAsset)).rejects.toThrow('expected');
  });
});
