# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory."""

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from studio_backend.api import system, ws
from studio_backend.errors import ERROR_RESPONSES, install_error_handlers
from studio_backend.events import SCHEMA_UNIONS
from studio_backend.security import SecurityConfig, SecurityMiddleware
from studio_backend.version import API_VERSION

DEFAULT_WS_PING_INTERVAL = 15.0


def create_app(
    security: SecurityConfig | None = None, ws_ping_interval: float = DEFAULT_WS_PING_INTERVAL
) -> FastAPI:
    """Build the app.

    Without `security`, a random token nobody knows locks every route except health.
    """
    config = SecurityConfig() if security is None else security
    app = FastAPI(title="Studio backend", version=API_VERSION)
    app.state.ws_ping_interval = ws_ping_interval
    install_error_handlers(app)
    app.include_router(system.router, responses=ERROR_RESPONSES)
    app.include_router(ws.router)
    # Added last = runs first: the security checks wrap CORS, which wraps the routes.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(SecurityMiddleware, config=config)
    _publish_websocket_models(app)
    return app


def _publish_websocket_models(app: FastAPI) -> None:
    """Add the WebSocket message models to `components.schemas` (ADR-0006: OpenAPI has no WS)."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            schemas = schema.setdefault("components", {}).setdefault("schemas", {})
            for name, adapter in SCHEMA_UNIONS.items():
                union = adapter.json_schema(
                    ref_template="#/components/schemas/{model}", mode="serialization"
                )
                schemas.update(union.pop("$defs", {}))
                schemas[name] = union
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
