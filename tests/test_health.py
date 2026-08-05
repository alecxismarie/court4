from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.main import app


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_endpoint_checks_postgresql() -> None:
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "storage": "ok"}


def test_readiness_returns_503_when_storage_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = SimpleNamespace(
        service=SimpleNamespace(ready=lambda: True),
        storage=SimpleNamespace(ready=lambda: False),
    )
    monkeypatch.setattr(routes, "get_persistence", lambda: runtime)
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "ok",
        "storage": "unavailable",
    }


def test_configured_frontend_origin_gets_cors_headers() -> None:
    client = TestClient(app)

    response = client.options(
        "/api/v1/analyses/missing-analysis",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
