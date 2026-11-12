from datetime import date
import hashlib
import hmac
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.v1.access_codes import (
    AccessCodeCreate,
    AccessCodeVerification,
    create_access_code,
    get_access_session,
    list_access_codes,
    register_with_access_code,
    revoke_access_code,
    submit_score_with_access_code,
    verify_access_code,
)
from app.api.v1.participants import ParticipantCreate, PersonCreate
from app.api.v1.scores import ScoreCreate
from app.core.config import Settings
from app.db.models import (
    AccessCode,
    AccessSession,
    Event,
    EventAccess,
    EventParticipant,
    Person,
    Score,
    Station,
    User,
)
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
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def access_setup(db_session):
    organizer = User(auth_subject="organizer", display_name="Organizer")
    event_record = Event(name="Kerfuffle", event_date=date(2026, 11, 12))
    db_session.add_all([organizer, event_record])
    db_session.flush()
    station = Station(
        event_id=event_record.id,
        name="Main",
        score_min=0,
        score_max=10,
        score_step=2,
    )
    db_session.add(station)
    db_session.flush()
    db_session.add(
        EventAccess(
            user_id=organizer.id,
            event_id=event_record.id,
            role="organizer",
        )
    )
    db_session.commit()
    return {"organizer": organizer, "event": event_record, "station": station}


def settings():
    return Settings(access_code_hash_secret="a" * 48)


def request():
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/public/access/verify",
            "headers": [],
            "client": ("192.0.2.10", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def issue_code(
    db_session,
    access_setup,
    role="registrar",
    station_id=None,
    code="REGA2TR8",
):
    return create_access_code(
        access_setup["event"].id,
        AccessCodeCreate(
            role=role,
            code=code,
            station_id=station_id,
        ),
        access_setup["organizer"],
        db_session,
        settings(),
    )


def verify(db_session, raw_code):
    return verify_access_code(
        AccessCodeVerification(code=raw_code),
        request(),
        db_session,
        settings(),
    )


def session_for(db_session, access_token):
    return get_access_session(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token),
        db_session,
        settings(),
    )


def test_codes_are_hashed_listed_without_secret_and_disabled_by_organizer(
    db_session, access_setup
):
    created = issue_code(db_session, access_setup)

    stored = db_session.get(AccessCode, created["id"])
    assert created["code"]
    assert stored.secret_hash != created["code"]
    assert stored.label == "Код регистратора"
    assert created["code"] == "REGA2TR8"
    assert created["is_active"] is True
    assert list_access_codes(
        access_setup["event"].id,
        access_setup["organizer"],
        db_session,
    ) == [{key: value for key, value in created.items() if key != "code"}]

    revoked = revoke_access_code(
        created["id"], access_setup["organizer"], db_session
    )
    assert revoked["is_active"] is False
    with pytest.raises(HTTPException) as error:
        verify(db_session, created["code"])
    assert error.value.status_code == 400


def test_registration_code_registers_in_its_event(
    db_session, access_setup
):
    code = issue_code(db_session, access_setup)
    grant = verify(db_session, code["code"])
    result = register_with_access_code(
        ParticipantCreate(
            person=PersonCreate(first_name="Ada", last_name="Lovelace")
        ),
        session_for(db_session, grant["access_token"]),
        db_session,
    )

    assert result["event_id"] == access_setup["event"].id
    assert result["registration_number"] == "000001"


def test_access_code_is_case_insensitive_and_cannot_be_reused(
    db_session, access_setup
):
    created = issue_code(db_session, access_setup)

    grant = verify(db_session, created["code"].lower())
    assert grant["role"] == "registrar"

    with pytest.raises(HTTPException) as error:
        issue_code(db_session, access_setup, code=created["code"].lower())
    assert error.value.status_code == 409


def test_legacy_long_codes_remain_usable_after_short_code_change(
    db_session, access_setup
):
    legacy_code = "legacy_code-token-1234567890"
    secret_hash = hmac.new(
        settings().access_code_hash_secret.encode(),
        legacy_code.encode(),
        hashlib.sha256,
    ).hexdigest()
    db_session.add(
        AccessCode(
            event_id=access_setup["event"].id,
            created_by_user_id=access_setup["organizer"].id,
            role="registrar",
            label="Legacy registration",
            secret_hash=secret_hash,
        )
    )
    db_session.commit()

    grant = verify(db_session, legacy_code)

    assert grant["role"] == "registrar"


@pytest.mark.parametrize("value", ["SHORT", "REGISTA0", "REGISTA1", "REGISTI8", "REGISTO8"])
def test_codes_must_use_the_short_unambiguous_format(value):
    with pytest.raises(ValidationError):
        AccessCodeCreate(role="registrar", code=value)


def test_station_code_is_already_scoped_and_checks_server_score_scale(
    db_session, access_setup
):
    participant = Person(first_name="Ada", last_name="Lovelace")
    db_session.add(participant)
    db_session.flush()
    registration = EventParticipant(
        event_id=access_setup["event"].id,
        person_id=participant.id,
        registration_number="000001",
        qr_token=UUID("a1111111-1111-4111-8111-111111111111"),
    )
    db_session.add(registration)
    db_session.commit()
    code = issue_code(
        db_session,
        access_setup,
        role="station_operator",
        station_id=access_setup["station"].id,
    )
    grant = verify(db_session, code["code"])
    session = session_for(db_session, grant["access_token"])

    result = submit_score_with_access_code(
        ScoreCreate(event_participant_id=registration.id, points=6),
        session,
        db_session,
    )
    assert result["station_id"] == access_setup["station"].id
    assert result["points"] == 6
    assert db_session.query(Score).count() == 1

    with pytest.raises(HTTPException) as error:
        submit_score_with_access_code(
            ScoreCreate(event_participant_id=registration.id, points=8),
            session,
            db_session,
        )
    assert error.value.status_code == 409


def test_revoking_code_invalidates_existing_sessions(db_session, access_setup):
    code = issue_code(db_session, access_setup)
    grant = verify(db_session, code["code"])
    revoke_access_code(code["id"], access_setup["organizer"], db_session)

    with pytest.raises(HTTPException) as error:
        session_for(db_session, grant["access_token"])
    assert error.value.status_code == 401
    assert db_session.query(AccessSession).count() == 1


def test_code_creation_requires_organizer_and_matching_station(
    db_session, access_setup
):
    another_user = User(auth_subject="other", display_name="Other")
    db_session.add(another_user)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        create_access_code(
            access_setup["event"].id,
                AccessCodeCreate(role="registrar", code="REGA2TR8"),
            another_user,
            db_session,
            settings(),
        )
    assert error.value.status_code == 403

    with pytest.raises(HTTPException) as error:
        issue_code(
            db_session,
            access_setup,
            role="station_operator",
            station_id=999,
        )
    assert error.value.status_code == 404


def test_code_rate_limiter_rejects_excessive_attempts(db_session, access_setup):
    for _ in range(31):
        try:
            verify(db_session, "AAAAAAAA")
        except HTTPException as error:
            assert error.status_code in {400, 429}

    with pytest.raises(HTTPException) as error:
        verify(db_session, "AAAAAAAA")
    assert error.value.status_code == 429
