# SPDX-License-Identifier: Apache-2.0
"""Versioned models for the files the studio persists, their JSON Schemas and migrations."""

from studio_config_schema.document import (
    BACKUP_DIR,
    Loaded,
    dump_bytes,
    dumps,
    load,
    loads,
    read,
    save,
    upgrade,
)
from studio_config_schema.envelope import Envelope, UtcTimestamp
from studio_config_schema.errors import ErrorReason, Issue, SchemaFileError
from studio_config_schema.ids import derive_project_id, is_taken, project_id_problem
from studio_config_schema.migrations import MigrationChainError, Migrations, MigrationStepError
from studio_config_schema.project import PROJECT_ID_PATTERN, ProjectFile

__all__ = [
    "BACKUP_DIR",
    "PROJECT_ID_PATTERN",
    "Envelope",
    "ErrorReason",
    "Issue",
    "Loaded",
    "MigrationChainError",
    "MigrationStepError",
    "Migrations",
    "ProjectFile",
    "SchemaFileError",
    "UtcTimestamp",
    "derive_project_id",
    "dump_bytes",
    "dumps",
    "is_taken",
    "load",
    "loads",
    "project_id_problem",
    "read",
    "save",
    "upgrade",
]
