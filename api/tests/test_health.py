from __future__ import annotations

import time

import pytest
from app.api import health as health_module
from app.main import app
from fastapi.testclient import TestClient
from psycopg_pool import PoolTimeout


def test_health_reports_ok_against_a_real_database() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_fails_fast_and_in_the_envelope_when_the_database_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DeadPool:
        def connection(self, timeout: float | None = None) -> object:
            raise PoolTimeout("couldn't get a connection")

    with TestClient(app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(app.state, "pool", DeadPool())
        started = time.monotonic()
        response = client.get("/api/v1/health")
        elapsed = time.monotonic() - started

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert elapsed < health_module.CONNECT_TIMEOUT_SECONDS + 1
