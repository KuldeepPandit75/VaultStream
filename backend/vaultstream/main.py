"""FastAPI application factory and entrypoint.

Run locally with:
    uvicorn vaultstream.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from vaultstream import __version__
from vaultstream.config import get_settings
from vaultstream.db import engine

logger = logging.getLogger("vaultstream")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks.

    Later tasks attach the vector matrix and KNN index here so the cost is
    paid once per process rather than per request.
    """
    settings = get_settings()
    logger.info(
        "VaultStream starting (env=%s, version=%s)", settings.environment, __version__
    )
    yield
    engine.dispose()
    logger.info("VaultStream stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="VaultStream API",
        version=__version__,
        description="Catalog, auth, watch history, and recommendations for VaultStream.",
        lifespan=lifespan,
    )

    # allow_credentials=True requires explicit origins; a wildcard is rejected
    # by browsers when cookies are in play.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    def health() -> dict[str, str]:
        """Always 200 while the process is serving requests."""
        return {"status": "ok", "version": __version__}

    @app.get("/health/ready", tags=["ops"], summary="Readiness probe")
    def health_ready() -> JSONResponse:
        """503 unless the database is reachable."""
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - surface any driver/network error
            logger.warning("Readiness check failed: %s", exc)
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "database": "unreachable"},
            )
        return JSONResponse(
            status_code=200, content={"status": "ok", "database": "ok"}
        )

    return app


app = create_app()
