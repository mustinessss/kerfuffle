from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import create_initial_admin
from app.core.config import Settings, get_settings
from app.db.models import User, UserSession
from app.db.session import Base, get_db
from app.main import app
from app.core.passwords import hash_token


@pytest.fixture
def auth_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.create_function(
            "btrim", 1, lambda value: None if value is None else value.strip()
        ),
    )
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as session:
            yield session

    test_settings = Settings(environment="development", access_code_hash_secret="a" * 48)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: test_settings
    with Session(engine) as session:
        create_initial_admin(session, "admin@example.test", "SecurePassword123")

    with TestClient(app) as client:
        yield client, engine

    app.dependency_overrides.clear()
    engine.dispose()


def login(client: TestClient, password: str = "SecurePassword123"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": "ADMIN@example.test", "password": password},
        headers={"Origin": "http://testserver"},
    )


def test_login_sets_http_only_session_and_csrf_cookies(auth_client):
    client, _ = auth_client

    response = login(client)

    assert response.status_code == 200
    assert response.json()["is_system_admin"] is True
    assert "kerfuffle_session" in response.cookies
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.cookies.get("kerfuffle_csrf")
    assert client.get("/api/v1/auth/me").json()["email"] == "admin@example.test"


def test_system_admin_creates_event_with_cookie_session(auth_client):
    client, _ = auth_client
    assert login(client).status_code == 200

    response = client.post(
        "/api/v1/events",
        json={"name": "Cookie-auth event", "event_date": "2026-11-18"},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": client.cookies.get("kerfuffle_csrf"),
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Cookie-auth event"


def test_event_creation_requires_authentication(auth_client):
    client, _ = auth_client

    response = client.post(
        "/api/v1/events",
        json={"name": "Unauthenticated event", "event_date": "2026-11-18"},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 401


def test_login_returns_same_generic_error_for_unknown_email_and_bad_password(auth_client):
    client, _ = auth_client

    wrong_password = login(client, "WrongPassword123")
    unknown_email = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.test", "password": "WrongPassword123"},
        headers={"Origin": "http://testserver"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_blocked_user_cannot_login(auth_client):
    client, engine = auth_client
    with Session(engine) as session:
        account = session.query(User).filter_by(email="admin@example.test").one()
        account.is_active = False
        session.commit()

    response = login(client)

    assert response.status_code == 401
    assert response.json()["detail"] == "Неверный email или пароль."


def test_login_rejects_untrusted_origin(auth_client):
    client, _ = auth_client

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.test", "password": "SecurePassword123"},
        headers={"Origin": "https://attacker.example"},
    )

    assert response.status_code == 403


def test_mutating_authenticated_requests_require_csrf(auth_client):
    client, _ = auth_client
    assert login(client).status_code == 200

    response = client.post("/api/v1/auth/logout", headers={"Origin": "http://testserver"})

    assert response.status_code == 403


def test_logout_revokes_the_current_session(auth_client):
    client, engine = auth_client
    assert login(client).status_code == 200
    csrf_token = client.cookies.get("kerfuffle_csrf")

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert client.get("/api/v1/auth/me").status_code == 401
    with Session(engine) as session:
        assert session.query(UserSession).one().revoked_at is not None


def test_idle_or_absolute_expired_session_is_rejected(auth_client):
    client, engine = auth_client
    assert login(client).status_code == 200
    session_token = client.cookies.get("kerfuffle_session")
    with Session(engine) as session:
        record = session.query(UserSession).filter_by(token_hash=hash_token(session_token)).one()
        record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()

    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_all_revokes_every_session(auth_client):
    client, engine = auth_client
    assert login(client).status_code == 200
    client.cookies.clear()
    assert login(client).status_code == 200
    csrf_token = client.cookies.get("kerfuffle_csrf")

    response = client.post(
        "/api/v1/auth/logout-all",
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    with Session(engine) as session:
        assert session.query(UserSession).filter(UserSession.revoked_at.is_(None)).count() == 0
