# SPDX-License-Identifier: Apache-2.0
"""System routes: health and version."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from studio_backend.version import API_VERSION, app_version

router = APIRouter(prefix="/api", tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class VersionResponse(BaseModel):
    app_version: str
    api_version: str


@router.get("/health", operation_id="getHealth")
def get_health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/version", operation_id="getVersion")
def get_version() -> VersionResponse:
    return VersionResponse(app_version=app_version(), api_version=API_VERSION)
