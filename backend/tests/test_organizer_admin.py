from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.v1.organizer_admin import (
    InvitationAccept,
    InvitationCreate,
    ResetPassword,
    ResetRequest,
    accept_invitation,
    complete_password_reset,
    create_invitation,
    create_manual_password_reset_link,
    revoke_invitation,
    request_password_reset,
)
from app.core.config import Settings
from app.core.passwords import hash_password, hash_token, verify_password
from app.db.models import OrganizerInvitation, PasswordResetToken, User, UserSession
from app.db.session import Base


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


def request_with_origin(origin: str = "http://localhost:5173") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/public/invitations/accept",
            "headers": [(b"origin", origin.encode()), (b"host", b"testserver")],
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
    )
    session.add(admin)
    session.commit()
    return admin


def create_test_invitation(session: Session, admin: User):
    return create_invitation(
        InvitationCreate(email="ORGANIZER@example.test"),
        admin,
        session,
        Settings(
            smtp_host=None,
            smtp_user=None,
            smtp_password=None,
            smtp_from=None,
        ),
    )


def production_manual_settings() -> Settings:
    return Settings(
        environment="production",
        database_url=(
            "postgresql+psycopg://kerfuffle_app:strong-password"
            "@db.example.test:5432/kerfuffle?sslmode=verify-full"
        ),
        access_code_hash_secret="a" * 48,
        app_public_url="https://kerfuffle.example.test",
        app_allowed_origins="https://kerfuffle.example.test",
        manual_auth_links_enabled=True,
        smtp_host=None,
        smtp_user=None,
        smtp_password=None,
        smtp_from=None,
    )


def test_non_system_admin_cannot_invite_organizer(db_session):
    regular_user = User(email="regular@example.test", display_name="Regular")
    db_session.add(regular_user)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        create_invitation(
            InvitationCreate(email="new@example.test"),
            regular_user,
            db_session,
            Settings(),
        )
    assert error.value.status_code == 403


def test_production_manual_invitation_returns_link_only_to_admin(db_session):
    admin = admin_user(db_session)

    result = create_invitation(
        InvitationCreate(email="manual@example.test"),
        admin,
        db_session,
        production_manual_settings(),
    )

    token = parse_qs(urlsplit(result["invitation_url"]).query)["token"][0]
    invitation = db_session.query(OrganizerInvitation).one()
    assert result["delivery_method"] == "manual"
    assert result["status"] == "sent"
    assert invitation.token_hash == hash_token(token)
    assert invitation.token_hash != token


def test_smtp_invitation_takes_precedence_over_manual_delivery(
    db_session,
    monkeypatch,
):
    admin = admin_user(db_session)
    sent_messages = []
    monkeypatch.setattr(
        "app.api.v1.organizer_admin.send_email",
        lambda *args: sent_messages.append(args),
    )
    settings = production_manual_settings().model_copy(
        update={
            "smtp_host": "smtp.example.test",
            "smtp_user": "mailer",
            "smtp_password": "mailer-password",
            "smtp_from": "noreply@example.test",
        }
    )

    result = create_invitation(
        InvitationCreate(email="email@example.test"),
        admin,
        db_session,
        settings,
    )

    assert result["delivery_method"] == "email"
    assert result["invitation_url"] is None
    assert len(sent_messages) == 1


def test_invitation_stores_only_token_hash_and_accepts_once(db_session):
    admin = admin_user(db_session)
    invitation_result = create_test_invitation(db_session, admin)
    token = parse_qs(urlsplit(invitation_result["invitation_url"]).query)["token"][0]
    invitation = db_session.query(OrganizerInvitation).one()

    assert invitation.email == "organizer@example.test"
    assert invitation.token_hash != token
    assert invitation.sent_at is not None

    result = accept_invitation(
        InvitationAccept(
            token=token,
            display_name="New Organizer",
            password="SecurePassword123",
        ),
        request_with_origin(),
        db_session,
        Settings(),
    )

    assert result == {"ok": True, "email": "organizer@example.test"}
    organizer = db_session.query(User).filter_by(email="organizer@example.test").one()
    assert organizer.is_organizer is True
    assert organizer.password_hash != "SecurePassword123"
    assert invitation.used_at is not None

    with pytest.raises(HTTPException) as error:
        accept_invitation(
            InvitationAccept(
                token=token,
                display_name="Duplicate",
                password="SecurePassword123",
            ),
            request_with_origin(),
            db_session,
            Settings(),
        )
    assert error.value.status_code == 400


def test_invitation_can_be_revoked_and_cannot_be_accepted(db_session):
    admin = admin_user(db_session)
    invitation_result = create_test_invitation(db_session, admin)
    token = parse_qs(urlsplit(invitation_result["invitation_url"]).query)["token"][0]
    invitation = db_session.query(OrganizerInvitation).one()

    assert revoke_invitation(invitation.id, admin, db_session) == {"ok": True}
    with pytest.raises(HTTPException) as error:
        accept_invitation(
            InvitationAccept(
                token=token,
                display_name="Organizer",
                password="SecurePassword123",
            ),
            request_with_origin(),
            db_session,
            Settings(),
        )
    assert error.value.status_code == 400


def test_expired_invitation_cannot_be_accepted(db_session):
    admin = admin_user(db_session)
    invitation_result = create_test_invitation(db_session, admin)
    token = parse_qs(urlsplit(invitation_result["invitation_url"]).query)["token"][0]
    invitation = db_session.query(OrganizerInvitation).one()
    invitation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        accept_invitation(
            InvitationAccept(
                token=token,
                display_name="Organizer",
                password="SecurePassword123",
            ),
            request_with_origin(),
            db_session,
            Settings(),
        )
    assert error.value.status_code == 400


def test_invitation_accept_rejects_bad_origin(db_session):
    admin = admin_user(db_session)
    invitation_result = create_test_invitation(db_session, admin)
    token = parse_qs(urlsplit(invitation_result["invitation_url"]).query)["token"][0]

    with pytest.raises(HTTPException) as error:
        accept_invitation(
            InvitationAccept(
                token=token,
                display_name="Organizer",
                password="SecurePassword123",
            ),
            request_with_origin("https://attacker.example"),
            db_session,
            Settings(),
        )
    assert error.value.status_code == 403


def test_password_reset_revokes_existing_sessions_and_is_single_use(db_session, monkeypatch):
    account = User(
        email="organizer@example.test",
        display_name="Organizer",
        password_hash=hash_password("SecurePassword123"),
        is_organizer=True,
    )
    db_session.add(account)
    db_session.flush()
    session_record = UserSession(
        user_id=account.id,
        token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
    )
    db_session.add(session_record)
    db_session.commit()

    sent_messages = []
    monkeypatch.setattr(
        "app.api.v1.organizer_admin.send_email",
        lambda settings, recipient, subject, body: sent_messages.append(body),
    )
    settings = Settings(
        smtp_host="smtp.example.test",
        smtp_user="mailer",
        smtp_password="mailer-password",
        smtp_from="noreply@example.test",
    )
    assert request_password_reset(
        ResetRequest(email="ORGANIZER@example.test"),
        request_with_origin(),
        db_session,
        settings,
    ) == {"ok": True}
    token = parse_qs(urlsplit(sent_messages[0].splitlines()[2]).query)["token"][0]

    result = complete_password_reset(
        ResetPassword(token=token, password="ReplacementPassword456"),
        request_with_origin(),
        db_session,
        settings,
    )
    assert result == {"ok": True}
    db_session.refresh(account)
    db_session.refresh(session_record)
    assert verify_password(account.password_hash, "ReplacementPassword456")
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
        "app.api.v1.organizer_admin.send_email",
        lambda *args: sent_messages.append(args),
    )
    result = request_password_reset(
        ResetRequest(email="unknown@example.test"),
        request_with_origin(),
        db_session,
        Settings(
            smtp_host="smtp.example.test",
            smtp_user="mailer",
            smtp_password="mailer-password",
            smtp_from="noreply@example.test",
        ),
    )
    assert result == {"ok": True}
    assert sent_messages == []


def test_superuser_can_create_a_local_reset_link(db_session):
    admin = admin_user(db_session)
    account = User(
        email="organizer@example.test",
        display_name="Organizer",
        password_hash=hash_password("SecurePassword123"),
        is_organizer=True,
    )
    db_session.add(account)
    db_session.commit()

    result = create_manual_password_reset_link(
        account.id,
        admin,
        db_session,
        Settings(app_public_url="http://localhost:5173"),
    )

    token = parse_qs(urlsplit(result["reset_url"]).query)["token"][0]
    reset = db_session.query(PasswordResetToken).one()
    assert result["expires_in_minutes"] == 30
    assert reset.token_hash == hash_token(token)
    assert reset.token_hash != token


def test_superuser_can_create_a_manual_reset_link_in_production(db_session):
    admin = admin_user(db_session)
    account = User(
        email="manual-reset@example.test",
        display_name="Organizer",
        password_hash=hash_password("SecurePassword123"),
        is_organizer=True,
    )
    db_session.add(account)
    db_session.commit()

    result = create_manual_password_reset_link(
        account.id,
        admin,
        db_session,
        production_manual_settings(),
    )

    token = parse_qs(urlsplit(result["reset_url"]).query)["token"][0]
    reset = db_session.query(PasswordResetToken).one()
    assert result["expires_in_minutes"] == 30
    assert reset.token_hash == hash_token(token)
    assert reset.token_hash != token


def test_non_system_admin_cannot_create_a_manual_reset_link(db_session):
    regular_user = User(email="regular@example.test", display_name="Regular")
    db_session.add(regular_user)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        create_manual_password_reset_link(
            1,
            regular_user,
            db_session,
            production_manual_settings(),
        )

    assert error.value.status_code == 403


@pytest.mark.parametrize("manual_links_enabled", [False, True])
def test_production_reset_link_is_hidden_when_manual_delivery_is_not_active(
    db_session,
    manual_links_enabled,
):
    admin = admin_user(db_session)
    account = User(
        email="reset-disabled@example.test",
        display_name="Organizer",
        password_hash=hash_password("SecurePassword123"),
        is_organizer=True,
    )
    db_session.add(account)
    db_session.commit()
    settings = production_manual_settings().model_copy(
        update={
            "manual_auth_links_enabled": manual_links_enabled,
            "smtp_host": "smtp.example.test",
            "smtp_user": "mailer",
            "smtp_password": "mailer-password",
            "smtp_from": "noreply@example.test",
        }
    )

    with pytest.raises(HTTPException) as error:
        create_manual_password_reset_link(account.id, admin, db_session, settings)

    assert error.value.status_code == 404
