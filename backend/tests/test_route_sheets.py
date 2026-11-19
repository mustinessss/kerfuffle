from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.api.v1.participants import ParticipantCreate, PersonCreate, register_participant_record
from app.api.v1.route_sheets import (
    RouteSheetCreate,
    RouteSheetUpdate,
    create_route_sheet,
    delete_route_sheet,
    list_route_sheets,
    update_route_sheet,
)
from app.api.v1.scores import (
    ParticipantLookup,
    ScoreCreate,
    create_score_record,
    lookup_participant_record,
)
from app.db.models import (
    Event,
    EventParticipant,
    Person,
    RouteSheet,
    RouteSheetStation,
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
def route_setup(db_session):
    admin = User(
        legacy_identity_subject="admin",
        display_name="Admin",
        is_system_admin=True,
    )
    registrar = User(legacy_identity_subject="registrar", display_name="Regular user")
    event_record = Event(name="Route event", event_date=date(2026, 11, 18))
    other_event = Event(name="Other event", event_date=date(2026, 11, 19))
    db_session.add_all([admin, registrar, event_record, other_event])
    db_session.flush()
    included_station = Station(
        event_id=event_record.id,
        name="North",
        score_min=0,
        score_max=10,
        score_step=1,
    )
    excluded_station = Station(
        event_id=event_record.id,
        name="South",
        score_min=0,
        score_max=10,
        score_step=1,
    )
    foreign_station = Station(
        event_id=other_event.id,
        name="Foreign",
        score_min=0,
        score_max=10,
        score_step=1,
    )
    db_session.add_all([included_station, excluded_station, foreign_station])
    db_session.flush()
    return {
        "event": event_record,
        "other_event": other_event,
        "admin": admin,
        "registrar": registrar,
        "included": included_station,
        "excluded": excluded_station,
        "foreign": foreign_station,
    }


def create_sheet(db_session, route_setup, *, capacity=None, stations=None):
    return create_route_sheet(
        route_setup["event"].id,
        RouteSheetCreate(
            name="North route",
            capacity=capacity,
            station_ids=stations or [route_setup["included"].id],
        ),
        route_setup["admin"],
        db_session,
    )


def test_admin_creates_and_lists_route_sheet(db_session, route_setup):
    sheet = create_sheet(db_session, route_setup, capacity=4)

    assert sheet["event_id"] == route_setup["event"].id
    assert sheet["capacity"] == 4
    assert sheet["registered_count"] == 0
    assert sheet["stations"] == [
        {"id": route_setup["included"].id, "name": "North"}
    ]
    assert list_route_sheets(
        route_setup["event"].id,
        route_setup["admin"],
        db_session,
    ) == [sheet]


def test_route_sheet_requires_event_stations_and_system_admin_access(
    db_session, route_setup
):
    with pytest.raises(HTTPException) as error:
        create_sheet(
            db_session,
            route_setup,
            stations=[route_setup["included"].id, route_setup["foreign"].id],
        )
    assert error.value.status_code == 404

    with pytest.raises(HTTPException) as error:
        create_route_sheet(
            route_setup["event"].id,
            RouteSheetCreate(name="Unauthorized", station_ids=[route_setup["included"].id]),
            route_setup["registrar"],
            db_session,
        )
    assert error.value.status_code == 403


def test_registration_requires_route_and_enforces_capacity(db_session, route_setup):
    sheet = create_sheet(db_session, route_setup, capacity=1)

    with pytest.raises(HTTPException) as error:
        register_participant_record(
            route_setup["event"].id,
            ParticipantCreate(
                person=PersonCreate(first_name="Missing", last_name="Route"),
                registration_number="000001",
            ),
            db_session,
        )
    assert error.value.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(Person)) == 0

    registered = register_participant_record(
        route_setup["event"].id,
        ParticipantCreate(
            person=PersonCreate(first_name="First", last_name="Participant"),
            route_sheet_id=sheet["id"],
            registration_number="000001",
        ),
        db_session,
    )
    assert registered["route_sheet_id"] == sheet["id"]
    assert registered["route_sheet_name"] == "North route"

    with pytest.raises(HTTPException) as error:
        register_participant_record(
            route_setup["event"].id,
            ParticipantCreate(
                person=PersonCreate(first_name="Second", last_name="Participant"),
                route_sheet_id=sheet["id"],
                registration_number="000002",
            ),
            db_session,
        )
    assert error.value.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Person)) == 1


def test_scoring_outside_assigned_route_does_not_change_membership(
    db_session, route_setup
):
    sheet = create_sheet(db_session, route_setup)
    registered = register_participant_record(
        route_setup["event"].id,
        ParticipantCreate(
            person=PersonCreate(first_name="Route", last_name="Participant"),
            route_sheet_id=sheet["id"],
            registration_number="000001",
        ),
        db_session,
    )

    lookup = lookup_participant_record(
        route_setup["excluded"].id,
        ParticipantLookup(registration_number=registered["registration_number"]),
        db_session,
    )
    assert lookup["event_participant_id"] == registered["id"]
    score = create_score_record(
        route_setup["excluded"].id,
        ScoreCreate(event_participant_id=registered["id"], points=5),
        db_session,
    )
    assert score["station_id"] == route_setup["excluded"].id
    included_score = create_score_record(
        route_setup["included"].id,
        ScoreCreate(event_participant_id=registered["id"], points=5),
        db_session,
    )
    assert included_score["station_id"] == route_setup["included"].id
    assert db_session.get(EventParticipant, registered["id"]).route_sheet_id == sheet["id"]


def test_route_sheet_cannot_be_deleted_after_assignment(db_session, route_setup):
    sheet = create_sheet(db_session, route_setup)
    register_participant_record(
        route_setup["event"].id,
        ParticipantCreate(
            person=PersonCreate(first_name="Route", last_name="Participant"),
            route_sheet_id=sheet["id"],
            registration_number="000001",
        ),
        db_session,
    )

    with pytest.raises(HTTPException) as error:
        delete_route_sheet(sheet["id"], route_setup["admin"], db_session)
    assert error.value.status_code == 409


def test_route_sheet_stations_can_be_edited_after_assignment(db_session, route_setup):
    sheet = create_sheet(db_session, route_setup)
    registered = register_participant_record(
        route_setup["event"].id,
        ParticipantCreate(
            person=PersonCreate(first_name="Route", last_name="Participant"),
            route_sheet_id=sheet["id"],
            registration_number="000001",
        ),
        db_session,
    )

    updated = update_route_sheet(
        sheet["id"],
        RouteSheetUpdate(
            name="Updated route",
            station_ids=[route_setup["excluded"].id],
        ),
        route_setup["admin"],
        db_session,
    )

    assert updated["name"] == "Updated route"
    assert updated["stations"] == [
        {"id": route_setup["excluded"].id, "name": "South"}
    ]
    assert db_session.get(EventParticipant, registered["id"]).route_sheet_id == sheet["id"]


@pytest.mark.skipif(
    not os.environ.get("KERFUFFLE_TEST_POSTGRES_URL"),
    reason="Set KERFUFFLE_TEST_POSTGRES_URL to a disposable PostgreSQL test database",
)
def test_postgresql_route_capacity_is_not_overbooked():
    database_url = os.environ["KERFUFFLE_TEST_POSTGRES_URL"]
    schema_name = f"route_test_{uuid4().hex}"
    admin_engine = create_engine(database_url)
    engine = None
    try:
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema_name}"')
        engine = create_engine(
            database_url,
            connect_args={"options": f"-csearch_path={schema_name}"},
            pool_size=4,
        )
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            event_record = Event(name="Concurrency", event_date=date(2026, 11, 18))
            people = [
                Person(first_name="First", last_name="Participant"),
                Person(first_name="Second", last_name="Participant"),
            ]
            session.add_all([event_record, *people])
            session.flush()
            station = Station(
                event_id=event_record.id,
                name="Only station",
                score_min=0,
                score_max=10,
                score_step=1,
            )
            sheet = RouteSheet(
                event_id=event_record.id,
                name="Single place",
                capacity=1,
            )
            session.add_all([station, sheet])
            session.flush()
            session.add(
                RouteSheetStation(
                    route_sheet_id=sheet.id,
                    event_id=event_record.id,
                    station_id=station.id,
                )
            )
            session.commit()
            event_id = event_record.id
            person_ids = [person.id for person in people]
            route_sheet_id = sheet.id

        barrier = Barrier(2)

        def register(person_id: int) -> int:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    register_participant_record(
                        event_id,
                        ParticipantCreate(
                            person_id=person_id,
                            route_sheet_id=route_sheet_id,
                            registration_number=f"{person_id:06d}",
                        ),
                        session,
                    )
                except HTTPException as error:
                    return error.status_code
                return 201

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(register, person_ids))

        assert sorted(results) == [201, 409]
        with Session(engine) as session:
            assert session.scalar(
                select(func.count())
                .select_from(EventParticipant)
                .where(EventParticipant.route_sheet_id == route_sheet_id)
            ) == 1
    finally:
        if engine is not None:
            engine.dispose()
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        admin_engine.dispose()
