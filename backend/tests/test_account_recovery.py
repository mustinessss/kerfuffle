from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.v1.account_recovery import (
    ResetPassword,
    ResetRequest,
    complete_password_reset,
    request_password_reset,
)
from app.core.config import Settings
from app.core.passwords import hash_password, verify_password
from app.db.models import PasswordResetToken, User, UserSession
from app.db.session import Base
from app.main import app


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.create_function(
            "btrim", 1, lambda value: None if value is None else value.strip()
        ),
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def request_with_origin() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/public/password-reset/request",
            "headers": [(b"origin", b"http://localhost:5173"), (b"host", b"testserver")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
        }
    )


def admin_user(session: Session) -> User:
    admin = User(
        email="admin@example.test",
        display_name="Admin",
        is_system_admin=True,
        password_hash=hash_password("SecurePassword123"),
    )
    session.add(admin)
    session.commit()
    return admin


def smtp_settings() -> Settings:
    return Settings(
        smtp_host="smtp.example.test",
        smtp_user="mailer",
        smtp_password="mailer-password",
        smtp_from="noreply@example.test",
    )


def test_admin_password_reset_revokes_sessions_and_is_single_use(db_session, monkeypatch):
    admin = admin_user(db_session)
    session_record = UserSession(
        user_id=admin.id,
        token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        last_activity_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
    )
    db_session.add(session_record)
    db_session.commit()

    sent_messages = []
    monkeypatch.setattr(
        "app.api.v1.account_recovery.send_email",
        lambda settings, recipient, subject, body: sent_messages.append(body),
    )
    settings = smtp_settings()
    assert request_password_reset(
        ResetRequest(email="ADMIN@example.test"),
        request_with_origin(),
        db_session,
        settings,
    ) == {"ok": True}
    token = parse_qs(urlsplit(sent_messages[0].splitlines()[2]).query)["token"][0]

    assert complete_password_reset(
        ResetPassword(token=token, password="ReplacementPassword456"),
        request_with_origin(),
        db_session,
        settings,
    ) == {"ok": True}
    db_session.refresh(admin)
    db_session.refresh(session_record)
    assert verify_password(admin.password_hash, "ReplacementPassword456")
    assert session_record.revoked_at is not None

    with pytest.raises(HTTPException) as error:
        complete_password_reset(
            ResetPassword(token=token, password="AnotherPassword789"),
            request_with_origin(),
            db_session,
            settings,
        )
    assert error.value.status_code == 400


def test_password_reset_request_is_generic_for_unknown_email(db_session, monkeypatch):
    sent_messages = []
    monkeypatch.setattr(
        "app.api.v1.account_recovery.send_email",
        lambda *args: sent_messages.append(args),
    )
    assert request_password_reset(
        ResetRequest(email="unknown@example.test"),
        request_with_origin(),
        db_session,
        smtp_settings(),
    ) == {"ok": True}
    assert sent_messages == []


def test_password_reset_request_does_not_send_links_to_employee_accounts(
    db_session, monkeypatch
):
    employee = User(
        email="employee@example.test",
        display_name="Employee",
        password_hash=hash_password("SecurePassword123"),
    )
    db_session.add(employee)
    db_session.commit()
    sent_messages = []
    monkeypatch.setattr(
        "app.api.v1.account_recovery.send_email",
        lambda *args: sent_messages.append(args),
    )

    assert request_password_reset(
        ResetRequest(email=employee.email),
        request_with_origin(),
        db_session,
        smtp_settings(),
    ) == {"ok": True}
    assert sent_messages == []
    assert db_session.query(PasswordResetToken).count() == 0


def test_employee_account_routes_are_not_exposed_in_openapi():
    paths = app.openapi()["paths"]
    removed_paths = {
        "/api/v1/public/invitations/accept",
        "/api/v1/system-admin/users",
        "/api/v1/system-admin/invitations",
        "/api/v1/stations/{station_id}/participants/lookup",
        "/api/v1/stations/{station_id}/scores",
        "/api/v1/me",
    }

    assert removed_paths.isdisjoint(paths)
