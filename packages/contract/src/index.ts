// SPDX-License-Identifier: Apache-2.0
// Public entry of @studio/contract (ADR-0006). WebSocket helpers (src/ws.ts) arrive with the /ws endpoint (TC-20).
import type { components } from './generated/schema';

export { createApiClient } from './client';
export type { ApiClient, ApiClientOptions } from './client';
export type { components, operations, paths } from './generated/schema';

type Schemas = components['schemas'];
export type HealthResponse = Schemas['HealthResponse'];
export type VersionResponse = Schemas['VersionResponse'];
export type ErrorResponse = Schemas['ErrorResponse'];
