from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.v1.events import EventCreate, EventUpdate, create_event, update_event
from app.core.auth import create_initial_admin
from app.db.models import Event, EventAccess, User
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


def test_system_admin_creates_event_without_event_role_record(db_session):
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
    assert db_session.query(EventAccess).count() == 0


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


def test_system_admin_can_update_event_details(db_session):
    admin = User(
        legacy_identity_subject="edit-admin",
        display_name="Admin",
        is_system_admin=True,
    )
    event_record = Event(
        name="Old name",
        event_date=datetime(2026, 11, 11).date(),
    )
    db_session.add_all([admin, event_record])
    db_session.commit()

    response = update_event(
        event_record.id,
        EventUpdate(name="  Updated event  ", event_date="2026-11-12"),
        admin,
        db_session,
    )

    assert response["name"] == "Updated event"
    assert response["event_date"] == datetime(2026, 11, 12).date()
    assert db_session.query(EventAccess).count() == 0


def test_station_holder_cannot_update_event_details(db_session):
    holder = User(legacy_identity_subject="event-holder", display_name="Holder")
    event_record = Event(
        name="Original",
        event_date=datetime(2026, 11, 11).date(),
    )
    db_session.add_all([holder, event_record])
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        update_event(
            event_record.id,
            EventUpdate(name="Unauthorized"),
            holder,
            db_session,
        )

    assert error.value.status_code == 403
    assert db_session.get(Event, event_record.id).name == "Original"


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


def test_create_admin_promotes_existing_legacy_identity(db_session):
    existing = User(
        legacy_identity_subject="legacy-identity",
        email="admin@example.test",
        display_name="Registered user",
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
