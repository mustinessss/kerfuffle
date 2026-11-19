from sqlalchemy.exc import SQLAlchemyError
from fastapi.testclient import TestClient

from app.api.v1 import health
from app.main import app

client = TestClient(app)


def test_root_returns_project_info():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "Kerfuffle API"


def test_api_responses_are_not_cacheable():
    response = client.get("/api/v1/health")

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_health_returns_service_unavailable_when_database_is_down(monkeypatch):
    def database_unavailable():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(health, "check_database_connection", database_unavailable)

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "api": "ok",
        "database": "unavailable",
    }
