from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.v1.events import EventCreate, create_event
from app.cli import bootstrap_system_admin
from app.core import auth
from app.core.auth import decode_access_token, get_current_user
from app.core.config import Settings
from app.core.permissions import require_event_access, require_station_access
from app.db.models import Event, EventAccess, Station, User
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


@pytest.fixture
def oidc_keys(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key=public_key)

    monkeypatch.setattr(auth, "get_jwks_client", lambda _: FakeJwksClient())
    return private_key


def make_token(private_key, **overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "provider-user-123",
        "iss": "https://identity.example.test/",
        "aud": "kerfuffle-api",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "name": "Organizer",
        "email": "organizer@example.test",
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def oidc_settings(**overrides):
    return Settings(
        oidc_issuer="https://identity.example.test/",
        oidc_audience="kerfuffle-api",
        oidc_jwks_url="https://identity.example.test/.well-known/jwks.json",
        **overrides,
    )


def test_missing_oidc_config_returns_service_unavailable():
    with pytest.raises(HTTPException) as error:
        decode_access_token(
            "token",
            Settings(
                oidc_issuer=None,
                oidc_audience=None,
                oidc_jwks_url=None,
            ),
        )

    assert error.value.status_code == 503


def test_access_token_requires_valid_issuer_audience_and_expiry(oidc_keys):
    settings = oidc_settings()
    token = make_token(oidc_keys)

    assert decode_access_token(token, settings)["sub"] == "provider-user-123"

    for bad_claims in (
        {"iss": "https://attacker.example.test/"},
        {"aud": "another-api"},
        {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    ):
        with pytest.raises(HTTPException) as error:
            decode_access_token(make_token(oidc_keys, **bad_claims), settings)
        assert error.value.status_code == 401


def test_only_configured_bootstrap_subject_becomes_system_admin(
    db_session, oidc_keys
):
    token = make_token(oidc_keys)
    user = get_current_user(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
        db_session,
        oidc_settings(oidc_bootstrap_admin_subject="provider-user-123"),
    )

    assert user.auth_subject == "provider-user-123"
    assert user.display_name == "Organizer"
    assert user.email == "organizer@example.test"
    assert user.is_system_admin is True


def test_other_unregistered_user_is_not_auto_provisioned(db_session, oidc_keys):
    token = make_token(oidc_keys)
    with pytest.raises(HTTPException) as error:
        get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            db_session,
            oidc_settings(oidc_bootstrap_admin_subject="someone-else"),
        )

    assert error.value.status_code == 403
    assert db_session.query(User).count() == 0


def test_event_access_requires_an_assigned_role(db_session):
    user = User(auth_subject="sub-1", display_name="User")
    event_record = Event(name="Conference", event_date=datetime(2026, 11, 11).date())
    db_session.add_all([user, event_record])
    db_session.flush()
    db_session.add(
        EventAccess(user_id=user.id, event_id=event_record.id, role="registrar")
    )
    db_session.flush()

    assert require_event_access(db_session, user, event_record.id)[0].role == "registrar"
    with pytest.raises(HTTPException) as error:
        require_event_access(db_session, user, event_record.id, {"organizer"})

    assert error.value.status_code == 403


def test_station_operator_only_has_access_to_assigned_station(db_session):
    user = User(auth_subject="sub-2", display_name="Operator")
    event_record = Event(name="Conference", event_date=datetime(2026, 11, 11).date())
    db_session.add_all([user, event_record])
    db_session.flush()
    assigned = Station(
        event_id=event_record.id,
        name="North",
        score_min=0,
        score_max=10,
        score_step=1,
    )
    other = Station(
        event_id=event_record.id,
        name="South",
        score_min=0,
        score_max=10,
        score_step=1,
    )
    db_session.add_all([assigned, other])
    db_session.flush()
    db_session.add(
        EventAccess(
            user_id=user.id,
            event_id=event_record.id,
            role="station_operator",
            station_id=assigned.id,
        )
    )
    db_session.flush()

    assert (
        require_station_access(
            db_session, user, assigned.id, {"station_operator"}
        ).station_id
        == assigned.id
    )
    with pytest.raises(HTTPException) as error:
        require_station_access(db_session, user, other.id, {"station_operator"})

    assert error.value.status_code == 403


def test_system_admin_creates_event_and_becomes_organizer(db_session):
    admin = User(
        auth_subject="admin-sub",
        display_name="Admin",
        is_system_admin=True,
    )
    db_session.add(admin)
    db_session.commit()

    response = create_event(
        EventCreate(name="  Kerfuffle  ", event_date="2026-11-11"),
        admin,
        db_session,
    )

    assert response["name"] == "Kerfuffle"
    access = db_session.query(EventAccess).one()
    assert access.user_id == admin.id
    assert access.role == "organizer"


def test_non_admin_cannot_create_event(db_session):
    user = User(auth_subject="user-sub", display_name="User")
    db_session.add(user)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        create_event(
            EventCreate(name="Conference", event_date="2026-11-11"),
            user,
            db_session,
        )

    assert error.value.status_code == 403
    assert db_session.query(Event).count() == 0


def test_provisioned_organizer_can_create_event(db_session):
    organizer = User(
        auth_subject="organizer-sub",
        display_name="Organizer",
        is_organizer=True,
    )
    db_session.add(organizer)
    db_session.commit()

    response = create_event(
        EventCreate(name="Community day", event_date="2026-11-11"),
        organizer,
        db_session,
    )

    assert response["name"] == "Community day"
    access = db_session.query(EventAccess).one()
    assert access.user_id == organizer.id
    assert access.role == "organizer"


def test_one_time_admin_bootstrap_creates_identity_without_password(db_session):
    user = bootstrap_system_admin(
        db_session,
        auth_subject="keycloak-subject",
        display_name="Initial administrator",
        email="admin@example.test",
    )

    assert user.is_system_admin is True
    assert user.auth_subject == "keycloak-subject"

    with pytest.raises(RuntimeError, match="already exists"):
        bootstrap_system_admin(
            db_session,
            auth_subject="another-subject",
            display_name="Another administrator",
        )


def test_one_time_admin_bootstrap_can_promote_existing_oidc_identity(db_session):
    existing = User(
        auth_subject="existing-subject",
        display_name="Registered organizer",
        is_organizer=True,
    )
    db_session.add(existing)
    db_session.commit()

    user = bootstrap_system_admin(
        db_session,
        auth_subject="existing-subject",
        display_name="System administrator",
    )

    assert user.id == existing.id
    assert user.is_system_admin is True
    assert user.is_organizer is True
