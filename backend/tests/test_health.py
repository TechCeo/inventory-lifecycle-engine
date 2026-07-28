import asyncio
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app import main as main_module
from app.core.config import get_settings
from app.db.session import get_db
from app.main import app


class AvailableDatabase:
    def execute(self, statement: object) -> None:
        assert str(statement) == "SELECT 1"


class UnavailableDatabase:
    def execute(self, statement: object) -> None:
        raise SQLAlchemyError("PostgreSQL is unavailable")


@pytest.fixture(autouse=True)
def avoid_real_database_pool_warmup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def noop_warm_database_pool() -> None:
        return None

    monkeypatch.setattr(main_module, "warm_database_pool", noop_warm_database_pool)


def test_healthz_reports_minimal_healthy_status() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_health_reports_process_metadata() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Expiry Notification API",
        "version": "0.1.0",
        "environment": get_settings().app_environment,
    }


def test_ready_succeeds_when_database_accepts_query() -> None:
    app.dependency_overrides[get_db] = lambda: AvailableDatabase()
    try:
        with TestClient(app) as client:
            response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "available"}


def test_ready_returns_503_when_database_is_unavailable() -> None:
    app.dependency_overrides[get_db] = lambda: UnavailableDatabase()
    try:
        with TestClient(app) as client:
            response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable."}


def test_versioned_health_route_is_available() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200


def test_versioned_healthz_route_is_available() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_lifespan_schedules_database_pool_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()

    async def tracked_warm_database_pool() -> None:
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(main_module, "warm_database_pool", tracked_warm_database_pool)
    application = main_module.create_app()

    with TestClient(application):
        assert started.wait(timeout=1)
        assert application.state.database_pool_warmup_task is not None
