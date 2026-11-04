# SPDX-License-Identifier: Apache-2.0
"""Workspace and projects: API models, the service the routes call, and its implementations."""

from studio_backend.hub import EventHub
from studio_backend.workspace.service import WorkspaceService
from studio_backend.workspace.stub import InMemoryWorkspaceService


def default_service(hub: EventHub) -> WorkspaceService:
    """The one switch between implementations. 0.2.0 starts on the in-memory stub (TC-35);
    the file-system service replaces it here (TC-36)."""
    return InMemoryWorkspaceService(hub)


__all__ = ["InMemoryWorkspaceService", "WorkspaceService", "default_service"]
