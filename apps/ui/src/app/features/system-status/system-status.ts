// SPDX-License-Identifier: Apache-2.0
// Health and version of the backend, read only through the generated client (TC-22).
import type { ApiClient, VersionResponse } from '@studio/contract';

export type HealthState = 'loading' | 'healthy' | 'unreachable' | 'unauthorised';

export interface SystemStatus {
  health: Exclude<HealthState, 'loading'>;
  version: VersionResponse | null;
}

/** Calls /api/health and /api/version. Never throws: transport errors mean `unreachable`. */
export async function checkSystemStatus(client: ApiClient | null): Promise<SystemStatus> {
  if (!client) {
    return { health: 'unreachable', version: null };
  }
  try {
    const [health, version] = await Promise.all([
      client.GET('/api/health'),
      client.GET('/api/version'),
    ]);
    if (health.response.status === 401 || version.response.status === 401) {
      return { health: 'unauthorised', version: null };
    }
    return {
      health: health.data?.status === 'ok' ? 'healthy' : 'unreachable',
      version: version.data ?? null,
    };
  } catch {
    return { health: 'unreachable', version: null };
  }
}
