# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory."""

from fastapi import FastAPI

from studio_backend.api import system
from studio_backend.errors import install_error_handlers
from studio_backend.version import API_VERSION


def create_app() -> FastAPI:
    app = FastAPI(title="Studio backend", version=API_VERSION)
    install_error_handlers(app)
    app.include_router(system.router)
    return app
