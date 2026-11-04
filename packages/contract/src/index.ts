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

// Workspace and projects (TC-35).
export type Workspace = Schemas['Workspace'];
export type OpenWorkspaceRequest = Schemas['OpenWorkspaceRequest'];
export type RecentWorkspaces = Schemas['RecentWorkspaces'];
export type RecentWorkspace = Schemas['RecentWorkspace'];
export type Project = Schemas['Project'];
export type ProjectFile = Schemas['ProjectFile'];
export type ProjectList = Schemas['ProjectList'];
export type CreateProjectRequest = Schemas['CreateProjectRequest'];
export type UpdateProjectRequest = Schemas['UpdateProjectRequest'];
export type DeletedProject = Schemas['DeletedProject'];
export type Problem = Schemas['Problem'];
export type FileProblem = Schemas['FileProblem'];
/** Codes of the workspace/project errors. `ErrorResponse.error.code` is a plain string: map unknown codes to a generic message. */
export type WorkspaceErrorCode = Schemas['WorkspaceErrorCode'];

// WebSocket messages (TC-20, TC-35).
export type WsClientMessage = Schemas['WsClientMessage'];
export type WsServerMessage = Schemas['WsServerMessage'];
/** A server message narrowed by its `type`, e.g. `WsServerEvent<'project.created'>`. */
export type WsServerEvent<T extends WsServerMessage['type']> = Extract<WsServerMessage, { type: T }>;
