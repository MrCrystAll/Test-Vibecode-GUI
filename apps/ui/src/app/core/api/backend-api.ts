// SPDX-License-Identifier: Apache-2.0
// The single generated-client instance for the whole UI (ADR-0006). Components never see the token.
import {
  EnvironmentProviders,
  Injectable,
  inject,
  provideAppInitializer,
  signal,
} from '@angular/core';
import { type ApiClient, createApiClient } from '@studio/contract';

import { BACKEND_CONNECTION_SOURCE } from './backend-connection';

@Injectable({ providedIn: 'root' })
export class BackendApi {
  private readonly source = inject(BACKEND_CONNECTION_SOURCE);
  private token: string | null = null;
  private readonly clientSignal = signal<ApiClient | null>(null);

  /** The typed client, or null when no backend connection could be resolved. */
  readonly client = this.clientSignal.asReadonly();

  /** Resolves the connection and creates the client. Never throws: failure leaves `client` null. */
  async connect(): Promise<void> {
    try {
      const connection = await this.source();
      this.token = connection.token;
      this.clientSignal.set(
        createApiClient({ baseUrl: connection.baseUrl, getToken: () => this.token }),
      );
    } catch (error) {
      console.warn('Backend connection unavailable:', error);
      this.token = null;
      this.clientSignal.set(null);
    }
  }
}

/** Connects to the backend before the first screen renders. */
export function provideBackendApi(): EnvironmentProviders {
  return provideAppInitializer(() => inject(BackendApi).connect());
}
