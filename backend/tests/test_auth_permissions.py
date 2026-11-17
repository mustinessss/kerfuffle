from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.v1.events import EventCreate, create_event
from app.core.auth import create_initial_admin
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


def test_event_access_requires_an_assigned_role(db_session):
    user = User(legacy_identity_subject="sub-1", display_name="User")
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
    user = User(legacy_identity_subject="sub-2", display_name="Operator")
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
        legacy_identity_subject="admin-sub",
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
    user = User(legacy_identity_subject="user-sub", display_name="User")
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


def test_organizer_cannot_create_unassigned_event(db_session):
    organizer = User(
        legacy_identity_subject="organizer-sub",
        display_name="Organizer",
        is_organizer=True,
    )
    db_session.add(organizer)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        create_event(
            EventCreate(name="Community day", event_date="2026-11-11"),
            organizer,
            db_session,
        )
    assert error.value.status_code == 403
    assert db_session.query(Event).count() == 0


def test_create_admin_hashes_password_and_only_allows_one(db_session):
    user = create_initial_admin(
        db_session,
        "  ADMIN@example.test ",
        "StrongPassword123",
    )

    assert user.is_system_admin is True
    assert user.email == "admin@example.test"
    assert user.password_hash != "StrongPassword123"
    from app.core.passwords import verify_password
    assert verify_password(user.password_hash, "StrongPassword123")

    with pytest.raises(RuntimeError, match="уже создан"):
        create_initial_admin(db_session, "other@example.test", "StrongPassword123")


def test_create_admin_rejects_weak_password_and_invalid_email(db_session):
    with pytest.raises(ValueError, match="корректный email"):
        create_initial_admin(db_session, "bad-email", "StrongPassword123")
    with pytest.raises(ValueError, match="12 символов"):
        create_initial_admin(db_session, "admin@example.test", "short")


def test_create_admin_promotes_existing_legacy_identity_without_losing_roles(db_session):
    existing = User(
        legacy_identity_subject="legacy-identity",
        email="admin@example.test",
        display_name="Registered organizer",
        is_organizer=True,
    )
    db_session.add(existing)
    db_session.commit()

    user = create_initial_admin(
        db_session,
        "ADMIN@example.test",
        "StrongPassword123",
    )

    assert user.id == existing.id
    assert user.is_system_admin is True
    assert user.is_organizer is True
