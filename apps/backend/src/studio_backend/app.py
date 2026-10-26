# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from studio_backend.api import system
from studio_backend.errors import ERROR_RESPONSES, install_error_handlers
from studio_backend.security import SecurityConfig, SecurityMiddleware
from studio_backend.version import API_VERSION


def create_app(security: SecurityConfig | None = None) -> FastAPI:
    """Build the app.

    Without `security`, a random token nobody knows locks every route except health.
    """
    config = SecurityConfig() if security is None else security
    app = FastAPI(title="Studio backend", version=API_VERSION)
    install_error_handlers(app)
    app.include_router(system.router, responses=ERROR_RESPONSES)
    # Added last = runs first: the security checks wrap CORS, which wraps the routes.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(SecurityMiddleware, config=config)
    return app
