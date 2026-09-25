"""
FastAPI application factory.

Production: 192.168.4.1:443, mTLS enforced.
Debug (--debug): 127.0.0.1:8080, no TLS, no mTLS, OpenAPI docs enabled.
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from glasshouse import config
from glasshouse.web.routes import (
    dashboard,
    export,
    filters,
    scan,
    settings,
    vendors,
)

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Glasshouse",
        version="0.1.0",
        docs_url="/docs" if config.DEBUG else None,
        redoc_url="/redoc" if config.DEBUG else None,
        openapi_url="/openapi.json" if config.DEBUG else None,
    )

    # mTLS middleware only in production
    if not config.DEBUG:
        from glasshouse.web.auth import MTLSMiddleware

        app.add_middleware(MTLSMiddleware)

    # Static assets (CSS, minimal JS)
    static_dir = Path(__file__).parent / "templates" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Routes
    app.include_router(dashboard.router)
    app.include_router(filters.router)
    app.include_router(vendors.router)
    app.include_router(export.router)
    app.include_router(settings.router)
    app.include_router(scan.router)

    @app.on_event("startup")
    async def on_startup():
        log.info("Glasshouse web UI started (debug=%s)", config.DEBUG)

    return app
