from datetime import date
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
    list_route_sheets_with_access_code,
    register_participant_with_access_code,
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
    EventParticipant,
    Person,
    Score,
    Station,
    RouteSheet,
    RouteSheetStation,
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
    organizer = User(
        legacy_identity_subject="admin",
        display_name="Admin",
        is_system_admin=True,
    )
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
    role="station_operator",
    station_id=None,
    code="REGA2TR8",
):
    if role == "station_operator" and station_id is None:
        station_id = access_setup["station"].id
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


def test_codes_are_hashed_encrypted_and_revealed_to_admin_until_disabled(
    db_session, access_setup
):
    created = issue_code(db_session, access_setup)

    stored = db_session.get(AccessCode, created["id"])
    assert created["code"]
    assert stored.secret_hash != created["code"]
    assert stored.encrypted_code != created["code"]
    assert stored.label == "Код площадки"
    assert created["code"] == "REGA2TR8"
    assert created["is_active"] is True
    assert list_access_codes(
        access_setup["event"].id,
        access_setup["organizer"],
        db_session,
        settings(),
    ) == [created]

    revoked = revoke_access_code(
        created["id"], access_setup["organizer"], db_session
    )
    assert revoked["is_active"] is False
    revoked_list = list_access_codes(
        access_setup["event"].id,
        access_setup["organizer"],
        db_session,
        settings(),
    )
    assert revoked_list[0]["code"] is None
    with pytest.raises(HTTPException) as error:
        verify(db_session, created["code"])
    assert error.value.status_code == 400


def test_only_system_admin_can_read_access_codes(db_session, access_setup):
    issue_code(db_session, access_setup)
    participant_user = User(
        legacy_identity_subject="participant-user",
        display_name="Participant",
        is_system_admin=False,
    )
    db_session.add(participant_user)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        list_access_codes(
            access_setup["event"].id,
            participant_user,
            db_session,
            settings(),
        )
    assert error.value.status_code == 403


def test_access_code_is_case_insensitive_and_cannot_be_reused(
    db_session, access_setup
):
    created = issue_code(db_session, access_setup)

    grant = verify(db_session, created["code"].lower())
    assert grant["role"] == "station_operator"

    with pytest.raises(HTTPException) as error:
        issue_code(db_session, access_setup, code=created["code"].lower())
    assert error.value.status_code == 409


@pytest.mark.parametrize("value", ["SHORT", "REGISTA0", "REGISTA1", "REGISTI8", "REGISTO8"])
def test_codes_must_use_the_short_unambiguous_format(value):
    with pytest.raises(ValidationError):
        AccessCodeCreate(
            role="station_operator",
            station_id=1,
            code=value,
        )


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
    )
    db_session.add(registration)
    db_session.commit()
    code = issue_code(db_session, access_setup)
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


def test_registrar_code_is_event_scoped_and_can_register_participant(
    db_session, access_setup
):
    sheet = RouteSheet(
        event_id=access_setup["event"].id,
        name="North route",
        capacity=2,
    )
    db_session.add(sheet)
    db_session.flush()
    db_session.add(
        RouteSheetStation(
            route_sheet_id=sheet.id,
            event_id=access_setup["event"].id,
            station_id=access_setup["station"].id,
        )
    )
    db_session.commit()

    created = issue_code(
        db_session,
        access_setup,
        role="registrar",
        code="REG2STR8",
    )
    assert created["role"] == "registrar"
    assert created["station_id"] is None
    assert created["label"] == "Код регистратора"
    grant = verify(db_session, created["code"])
    assert grant["role"] == "registrar"
    assert grant["station"] is None
    access = session_for(db_session, grant["access_token"])

    sheets = list_route_sheets_with_access_code(access, db_session)
    assert [item["name"] for item in sheets] == ["North route"]
    participant = register_participant_with_access_code(
        ParticipantCreate(
            person=PersonCreate(
                first_name="New",
                last_name="Participant",
                phone="+70000000000",
                workplace_or_study="Example school",
            ),
            route_sheet_id=sheet.id,
            registration_number="123456",
        ),
        access,
        db_session,
    )
    assert participant == {"registration_number": "123456"}
    registration = db_session.query(EventParticipant).filter_by(
        event_id=access_setup["event"].id,
        registration_number="123456",
    ).one()
    assert registration.route_sheet_id == sheet.id
    person = db_session.get(Person, registration.person_id)
    assert person.phone == "+70000000000"
    assert person.workplace_or_study == "Example school"

    with pytest.raises(HTTPException) as error:
        submit_score_with_access_code(
            ScoreCreate(event_participant_id=registration.id, points=2),
            access,
            db_session,
        )
    assert error.value.status_code == 403


def test_registrar_code_cannot_be_scoped_to_station(db_session, access_setup):
    with pytest.raises(ValidationError):
        create_access_code(
            access_setup["event"].id,
            AccessCodeCreate(
                role="registrar",
                station_id=access_setup["station"].id,
                code="REG2STR8",
            ),
            access_setup["organizer"],
            db_session,
            settings(),
        )


def test_revoking_code_invalidates_existing_sessions(db_session, access_setup):
    code = issue_code(db_session, access_setup)
    grant = verify(db_session, code["code"])
    revoke_access_code(code["id"], access_setup["organizer"], db_session)

    with pytest.raises(HTTPException) as error:
        session_for(db_session, grant["access_token"])
    assert error.value.status_code == 401
    assert db_session.query(AccessSession).count() == 1


def test_code_creation_requires_system_admin_and_matching_station(
    db_session, access_setup
):
    another_user = User(legacy_identity_subject="other", display_name="Other")
    db_session.add(another_user)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        create_access_code(
            access_setup["event"].id,
            AccessCodeCreate(
                role="station_operator",
                station_id=access_setup["station"].id,
                code="REGA2TR8",
            ),
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
