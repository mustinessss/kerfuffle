from datetime import date

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.v1.participants import (
    ParticipantCreate,
    PersonCreate,
    list_participants,
    register_participant,
    search_people,
)
from app.api.v1.scores import ParticipantLookup
from app.api.v1.stations import (
    StationCreate,
    StationUpdate,
    create_station,
    list_stations,
    update_station,
)
from app.db.models import (
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
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def event_team(db_session):
    admin = User(legacy_identity_subject="admin", display_name="Admin", is_system_admin=True)
    registrar = User(legacy_identity_subject="registrar", display_name="Registrar")
    operator = User(legacy_identity_subject="operator", display_name="Operator")
    event_record = Event(name="Kerfuffle", event_date=date(2026, 11, 11))
    db_session.add_all([admin, registrar, operator, event_record])
    db_session.flush()
    return event_record, admin, registrar, operator


def test_admin_creates_station_and_regular_users_cannot_list_it(
    db_session, event_team
):
    event_record, admin, registrar, _ = event_team
    response = create_station(
        event_record.id,
        StationCreate(
            name="  Main stage ",
            score_min=0,
            score_max=10,
            score_step=2,
        ),
        admin,
        db_session,
    )

    assert response == {
        "id": response["id"],
        "event_id": event_record.id,
        "name": "Main stage",
        "score_min": 0,
        "score_max": 10,
        "score_step": 2,
    }
    with pytest.raises(HTTPException):
        list_stations(event_record.id, registrar, db_session)


def test_only_system_admin_can_create_or_update_stations(db_session, event_team):
    event_record, admin, registrar, _ = event_team

    with pytest.raises(HTTPException) as error:
        create_station(
            event_record.id,
            StationCreate(name="Stage", score_min=0, score_max=5, score_step=1),
            registrar,
            db_session,
        )
    assert error.value.status_code == 403

    station = Station(
        event_id=event_record.id,
        name="Stage",
        score_min=0,
        score_max=5,
        score_step=1,
    )
    db_session.add(station)
    db_session.flush()
    with pytest.raises(HTTPException) as error:
        update_station(
            station.id,
            StationUpdate(name="New name"),
            registrar,
            db_session,
        )
    assert error.value.status_code == 403


def test_station_operator_only_sees_assigned_station(db_session, event_team):
    event_record, admin, _, operator = event_team
    assigned = Station(
        event_id=event_record.id,
        name="Assigned",
        score_min=0,
        score_max=5,
        score_step=1,
    )
    unassigned = Station(
        event_id=event_record.id,
        name="Unassigned",
        score_min=0,
        score_max=5,
        score_step=1,
    )
    db_session.add_all([assigned, unassigned])
    db_session.flush()
    db_session.add(
        EventAccess(
            user_id=operator.id,
            event_id=event_record.id,
            role="station_operator",
            station_id=assigned.id,
        )
    )
    db_session.flush()

    organizer_stations = list_stations(event_record.id, admin, db_session)
    operator_stations = list_stations(event_record.id, operator, db_session)

    assert len(organizer_stations) == 2
    assert [station["id"] for station in operator_stations] == [assigned.id]


def test_station_scale_validation_and_post_score_lock(db_session, event_team):
    event_record, admin, _, _ = event_team
    with pytest.raises(ValidationError):
        StationCreate(name="Stage", score_min=0, score_max=5, score_step=2)

    station = Station(
        event_id=event_record.id,
        name="Stage",
        score_min=0,
        score_max=5,
        score_step=1,
    )
    person = Person(first_name="Alex", last_name="Example")
    db_session.add_all([station, person])
    db_session.flush()
    registration = EventParticipant(
        event_id=event_record.id,
        person_id=person.id,
        registration_number="000001",
    )
    db_session.add(registration)
    db_session.flush()
    db_session.add(
        Score(
            event_participant_id=registration.id,
            station_id=station.id,
            points=2,
        )
    )
    db_session.flush()

    with pytest.raises(HTTPException) as error:
        update_station(
            station.id,
            StationUpdate(score_max=10),
            admin,
            db_session,
        )
    assert error.value.status_code == 409

    response = update_station(
        station.id,
        StationUpdate(name="Updated name"),
        admin,
        db_session,
    )
    assert response["name"] == "Updated name"


def test_registration_creates_person_with_manual_six_digit_number(
    db_session, event_team
):
    event_record, admin, _, _ = event_team
    response = register_participant(
        event_record.id,
        ParticipantCreate(
            person=PersonCreate(
                first_name="  Alex ",
                last_name=" Example ",
                phone="  +70000000000 ",
                workplace_or_study="  Example school ",
            ),
            registration_number="482019",
        ),
        admin,
        db_session,
    )

    assert response["registration_number"] == "482019"
    assert response["first_name"] == "Alex"
    assert response["last_name"] == "Example"
    assert "qr_token" not in response
    person = db_session.query(Person).one()
    assert person.phone == "+70000000000"
    assert person.workplace_or_study == "Example school"


def test_registration_reuses_person_and_rejects_duplicate(
    db_session, event_team
):
    event_record, admin, _, _ = event_team
    person = Person(first_name="Alex", last_name="Example")
    db_session.add(person)
    db_session.flush()
    first = register_participant(
        event_record.id,
        ParticipantCreate(person_id=person.id, registration_number="000001"),
        admin,
        db_session,
    )
    second_person = Person(first_name="Jordan", last_name="Example")
    db_session.add(second_person)
    db_session.flush()
    second = register_participant(
        event_record.id,
        ParticipantCreate(person_id=second_person.id, registration_number="000002"),
        admin,
        db_session,
    )

    assert first["registration_number"] == "000001"
    assert second["registration_number"] == "000002"
    assert "qr_token" not in first

    with pytest.raises(HTTPException) as error:
        register_participant(
            event_record.id,
            ParticipantCreate(person_id=person.id, registration_number="000003"),
            admin,
            db_session,
        )
    assert error.value.status_code == 409
    assert db_session.query(EventParticipant).count() == 2


def test_registration_lookup_requires_six_numeric_digits_and_rejects_qr_fields():
    with pytest.raises(ValidationError):
        ParticipantLookup(registration_number="123")

    with pytest.raises(ValidationError):
        ParticipantLookup(registration_number="12A456")

    with pytest.raises(ValidationError):
        ParticipantLookup(qr_token="a1111111-1111-4111-8111-111111111111")


def test_registration_number_must_be_six_digits():
    with pytest.raises(ValidationError):
        ParticipantCreate(
            person=PersonCreate(first_name="Alex", last_name="Example"),
            registration_number="12345",
        )
    with pytest.raises(ValidationError):
        ParticipantCreate(
            person=PersonCreate(first_name="Alex", last_name="Example"),
            registration_number="12A456",
        )


def test_registration_requires_system_admin(db_session, event_team):
    event_record, _, _, operator = event_team
    with pytest.raises(HTTPException) as error:
        register_participant(
            event_record.id,
            ParticipantCreate(
                person=PersonCreate(first_name="Alex", last_name="Example"),
                registration_number="123456",
            ),
            operator,
            db_session,
        )

    assert error.value.status_code == 403
    assert db_session.query(Person).count() == 0


def test_people_search_and_participant_list_hide_optional_personal_data(
    db_session, event_team
):
    event_record, admin, _, _ = event_team
    person = Person(
        first_name="Alex",
        last_name="Example",
        phone="+70000000000",
        workplace_or_study="Private workplace",
    )
    db_session.add(person)
    db_session.flush()
    register_participant(
        event_record.id,
        ParticipantCreate(person_id=person.id, registration_number="000001"),
        admin,
        db_session,
    )

    results = search_people(event_record.id, "alex example", 20, admin, db_session)
    participants = list_participants(event_record.id, 100, 0, admin, db_session)

    assert results == [{"id": person.id, "first_name": "Alex", "last_name": "Example"}]
    assert "phone" not in participants[0]
    assert "workplace_or_study" not in participants[0]
    assert participants[0]["registration_number"] == "000001"
