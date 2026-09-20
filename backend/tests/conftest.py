"""Shared pytest fixtures.

Database tests run against a dedicated test database (docker-compose service
``db-test`` on host port 5434) so they never touch development data. Each test
runs inside a transaction that is rolled back afterwards, so tests are isolated
and order-independent.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from vaultstream.config import get_settings
from vaultstream.db import Base, get_db
from vaultstream.main import create_app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://vaultstream:vaultstream@localhost:5434/vaultstream_test",
)


def _database_reachable(url: str) -> bool:
    try:
        probe = create_engine(url, pool_pre_ping=True)
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
        probe.dispose()
    except Exception:  # noqa: BLE001 - any failure means "not reachable"
        return False
    return True


@pytest.fixture(scope="session", autouse=True)
def _disable_tmdb_by_default() -> Generator[None, None, None]:
    """Guarantee the suite never reaches TMDB.

    ``get_movie_detail`` resolves media lazily, so once a real TMDB_API_KEY is
    present in backend/.env the tests would make live API calls and assert
    against whatever TMDB happens to return. Clearing the key makes
    ``media_service.resolve`` degrade to None; tests that need media state insert
    rows directly, and the ones exercising the HTTP client mock the transport.
    """
    original = os.environ.get("TMDB_API_KEY")
    os.environ["TMDB_API_KEY"] = ""
    get_settings.cache_clear()
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("TMDB_API_KEY", None)
        else:
            os.environ["TMDB_API_KEY"] = original
        get_settings.cache_clear()


@pytest.fixture(scope="session")
def db_engine() -> Generator[Engine, None, None]:
    """Session-scoped engine against the test database, with schema created."""
    if not _database_reachable(TEST_DATABASE_URL):
        pytest.skip(
            "Test database unreachable. Start it with: "
            "docker compose up -d db-test"
        )

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True, future=True)

    # Extensions the schema depends on (trigram search on movie titles).
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    # Import registers all models on Base.metadata.
    import vaultstream.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """A session bound to a transaction that is always rolled back.

    Nested SAVEPOINTs let the code under test call ``commit()`` without
    escaping the outer transaction.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """API client with no database override (safe for DB-free endpoints)."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def db_client(db_session: Session) -> Generator[TestClient, None, None]:
    """API client whose ``get_db`` dependency yields the rolled-back session."""
    app = create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
