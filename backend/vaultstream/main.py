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
from vaultstream.api import auth as auth_router
from vaultstream.api import history as history_router
from vaultstream.api import movies as movies_router
from vaultstream.api import people as people_router
from vaultstream.api import recommendations as recommendations_router
from vaultstream.config import get_settings
from vaultstream.db import engine
from vaultstream.services import recommender

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

    # Warm the recommendation matrix so the first request does not pay for it.
    # Failure is non-fatal: the catalogue must still serve without recommendations.
    try:
        index = recommender.get_index()
        logger.info(
            "Vector index ready: %s rows, %s non-zeros",
            f"{index.n_rows:,}",
            f"{index.matrix.nnz:,}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Vector index unavailable (%s). Recommendations will be disabled until "
            "`python -m etl.vectors` has been run.",
            exc,
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

    app.include_router(auth_router.router)
    app.include_router(history_router.router)
    app.include_router(movies_router.router)
    app.include_router(people_router.router)
    app.include_router(recommendations_router.router)

    return app


app = create_app()
