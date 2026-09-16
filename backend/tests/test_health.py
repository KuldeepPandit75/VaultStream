"""Task 1 acceptance: the app boots, health probes behave, CORS is configured."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

import vaultstream.main as main_module
from vaultstream import __version__


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_openapi_schema_renders(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "VaultStream API"


def test_cors_allows_frontend_origin_with_credentials(client: TestClient) -> None:
    """Cookie-based auth needs an explicit origin echoed back, never '*'."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_readiness_ok_when_database_reachable(
    monkeypatch: pytest.MonkeyPatch, db_engine: Engine
) -> None:
    """Readiness reports the database as ok when a real connection succeeds."""
    monkeypatch.setattr(main_module, "engine", db_engine)
    with TestClient(main_module.create_app()) as probe:
        response = probe.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_readiness_503_when_database_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness must fail closed, not report ok, when the database is down."""
    dead_engine = create_engine(
        "postgresql+psycopg://nobody:nobody@127.0.0.1:1/nonexistent",
        connect_args={"connect_timeout": 1},
    )
    monkeypatch.setattr(main_module, "engine", dead_engine)
    with TestClient(main_module.create_app()) as probe:
        response = probe.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"
    dead_engine.dispose()
