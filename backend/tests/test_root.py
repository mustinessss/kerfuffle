from fastapi.testclient import TestClient
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
