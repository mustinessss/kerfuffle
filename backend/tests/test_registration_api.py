from datetime import date
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.v1.participants import (
    ParticipantCreate,
    PersonCreate,
    _next_registration_number,
    list_participants,
    register_participant,
    search_people,
)
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
    organizer = User(auth_subject="organizer", display_name="Organizer")
    registrar = User(auth_subject="registrar", display_name="Registrar")
    operator = User(auth_subject="operator", display_name="Operator")
    event_record = Event(name="Kerfuffle", event_date=date(2026, 11, 11))
    db_session.add_all([organizer, registrar, operator, event_record])
    db_session.flush()
    db_session.add_all(
        [
            EventAccess(
                user_id=organizer.id,
                event_id=event_record.id,
                role="organizer",
            ),
            EventAccess(
                user_id=registrar.id,
                event_id=event_record.id,
                role="registrar",
            ),
        ]
    )
    db_session.flush()
    return event_record, organizer, registrar, operator


def test_organizer_creates_station_and_registrar_can_list_it(
    db_session, event_team
):
    event_record, organizer, registrar, _ = event_team
    response = create_station(
        event_record.id,
        StationCreate(
            name="  Main stage ",
            score_min=0,
            score_max=10,
            score_step=2,
        ),
        organizer,
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
    assert list_stations(event_record.id, registrar, db_session) == [response]


def test_only_organizer_can_create_or_update_stations(db_session, event_team):
    event_record, organizer, registrar, _ = event_team

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
    event_record, organizer, _, operator = event_team
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

    organizer_stations = list_stations(event_record.id, organizer, db_session)
    operator_stations = list_stations(event_record.id, operator, db_session)

    assert len(organizer_stations) == 2
    assert [station["id"] for station in operator_stations] == [assigned.id]


def test_station_scale_validation_and_post_score_lock(db_session, event_team):
    event_record, organizer, _, _ = event_team
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
        registration_number="0001",
        qr_token=UUID("c2374ab2-b22c-4c41-8de0-54c662f18503"),
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
            organizer,
            db_session,
        )
    assert error.value.status_code == 409

    response = update_station(
        station.id,
        StationUpdate(name="Updated name"),
        organizer,
        db_session,
    )
    assert response["name"] == "Updated name"


def test_registration_creates_person_sequential_number_and_random_qr(
    db_session, event_team
):
    event_record, _, registrar, _ = event_team
    response = register_participant(
        event_record.id,
        ParticipantCreate(
            person=PersonCreate(
                first_name="  Alex ",
                last_name=" Example ",
                phone="  +70000000000 ",
            )
        ),
        registrar,
        db_session,
    )

    assert response["registration_number"] == "000001"
    assert response["first_name"] == "Alex"
    assert response["last_name"] == "Example"
    UUID(response["qr_token"])
    assert "phone" not in response


def test_registration_reuses_person_and_rejects_duplicate(
    db_session, event_team
):
    event_record, _, registrar, _ = event_team
    person = Person(first_name="Alex", last_name="Example")
    db_session.add(person)
    db_session.flush()
    first = register_participant(
        event_record.id,
        ParticipantCreate(person_id=person.id),
        registrar,
        db_session,
    )
    second_person = Person(first_name="Jordan", last_name="Example")
    db_session.add(second_person)
    db_session.flush()
    second = register_participant(
        event_record.id,
        ParticipantCreate(person_id=second_person.id),
        registrar,
        db_session,
    )

    assert first["registration_number"] == "000001"
    assert second["registration_number"] == "000002"
    assert first["qr_token"] != second["qr_token"]

    with pytest.raises(HTTPException) as error:
        register_participant(
            event_record.id,
            ParticipantCreate(person_id=person.id),
            registrar,
            db_session,
        )
    assert error.value.status_code == 409
    assert db_session.query(EventParticipant).count() == 2


def test_registration_number_limit_is_six_digits():
    assert _next_registration_number(0) == "000001"
    assert _next_registration_number(999_998) == "999999"
    with pytest.raises(HTTPException) as error:
        _next_registration_number(999_999)
    assert error.value.status_code == 409


def test_registration_requires_registrar_or_organizer(db_session, event_team):
    event_record, _, _, operator = event_team
    with pytest.raises(HTTPException) as error:
        register_participant(
            event_record.id,
            ParticipantCreate(
                person=PersonCreate(first_name="Alex", last_name="Example")
            ),
            operator,
            db_session,
        )

    assert error.value.status_code == 403
    assert db_session.query(Person).count() == 0


def test_people_search_and_participant_list_hide_optional_personal_data(
    db_session, event_team
):
    event_record, _, registrar, _ = event_team
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
        ParticipantCreate(person_id=person.id),
        registrar,
        db_session,
    )

    results = search_people(event_record.id, "alex example", 20, registrar, db_session)
    participants = list_participants(event_record.id, 100, 0, registrar, db_session)

    assert results == [{"id": person.id, "first_name": "Alex", "last_name": "Example"}]
    assert "phone" not in participants[0]
    assert "workplace_or_study" not in participants[0]
    assert participants[0]["registration_number"] == "000001"
