from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import uuid4
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.api.v1.leaderboard import list_public_events, read_public_leaderboard
from app.api.v1.scores import (
    ParticipantLookup,
    ScoreAnnulment,
    ScoreCreate,
    ScoreUpdate,
    annul_score,
    create_score_record,
    list_event_scores,
    lookup_participant_record,
    update_score,
)
from app.db.models import (
    Event,
    EventParticipant,
    Person,
    RouteSheet,
    RouteSheetStation,
    Score,
    ScoreAudit,
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
def scoring_setup(db_session):
    organizer = User(
        legacy_identity_subject="admin",
        display_name="Admin",
        is_system_admin=True,
    )
    operator = User(legacy_identity_subject="operator", display_name="Operator")
    event_record = Event(name="Kerfuffle", event_date=date(2026, 11, 11))
    other_event = Event(name="Other", event_date=date(2026, 11, 12))
    db_session.add_all([organizer, operator, event_record, other_event])
    db_session.flush()
    station = Station(
        event_id=event_record.id,
        name="Main",
        score_min=0,
        score_max=10,
        score_step=2,
    )
    another_station = Station(
        event_id=event_record.id,
        name="Side",
        score_min=0,
        score_max=4,
        score_step=2,
    )
    other_station = Station(
        event_id=other_event.id,
        name="Other event station",
        score_min=0,
        score_max=10,
        score_step=1,
    )
    db_session.add_all([station, another_station, other_station])
    db_session.flush()

    people = [
        Person(first_name="Ada", last_name="One", phone="private"),
        Person(first_name="Bea", last_name="Two"),
        Person(first_name="Cal", last_name="Three"),
        Person(first_name="Other", last_name="Event"),
    ]
    db_session.add_all(people)
    db_session.flush()
    registrations = [
        EventParticipant(
            event_id=event_record.id,
            person_id=people[0].id,
            registration_number="000001",
        ),
        EventParticipant(
            event_id=event_record.id,
            person_id=people[1].id,
            registration_number="000002",
        ),
        EventParticipant(
            event_id=event_record.id,
            person_id=people[2].id,
            registration_number="000003",
        ),
        EventParticipant(
            event_id=other_event.id,
            person_id=people[3].id,
            registration_number="000001",
        ),
    ]
    db_session.add_all(registrations)
    db_session.flush()
    return {
        "event": event_record,
        "other_event": other_event,
        "organizer": organizer,
        "operator": operator,
        "station": station,
        "another_station": another_station,
        "other_station": other_station,
        "registrations": registrations,
        "people": people,
    }


def test_participant_lookup_uses_six_digit_number(
    db_session, scoring_setup
):
    station = scoring_setup["station"]
    number_result = lookup_participant_record(
        station.id,
        ParticipantLookup(registration_number="000001"),
        db_session,
    )

    assert number_result["first_name"] == "Ada"
    assert number_result["already_scored"] is False
    assert "phone" not in number_result


def test_score_record_can_be_created_once_and_lookup_shows_it(
    db_session, scoring_setup
):
    station = scoring_setup["station"]
    registration = scoring_setup["registrations"][0]
    score = create_score_record(
        station.id,
        ScoreCreate(event_participant_id=registration.id, points=6),
        db_session,
    )

    assert score["points"] == 6
    lookup = lookup_participant_record(
        station.id,
        ParticipantLookup(registration_number="000001"),
        db_session,
    )
    assert lookup["already_scored"] is True
    assert lookup["score"]["id"] == score["id"]

    with pytest.raises(HTTPException) as error:
        create_score_record(
            station.id,
            ScoreCreate(event_participant_id=registration.id, points=8),
            db_session,
        )
    assert error.value.status_code == 409
    assert db_session.query(Score).count() == 1


def test_score_validation_rejects_bad_scale_and_wrong_event(
    db_session, scoring_setup
):
    station = scoring_setup["station"]

    with pytest.raises(HTTPException) as error:
        create_score_record(
            station.id,
            ScoreCreate(
                event_participant_id=scoring_setup["registrations"][0].id,
                points=5,
            ),
            db_session,
        )
    assert error.value.status_code == 422

    with pytest.raises(HTTPException) as error:
        create_score_record(
            station.id,
            ScoreCreate(
                event_participant_id=scoring_setup["registrations"][3].id,
                points=6,
            ),
            db_session,
        )
    assert error.value.status_code == 404


def test_only_system_admin_can_correct_a_score(db_session, scoring_setup):
    station = scoring_setup["station"]
    registration = scoring_setup["registrations"][0]
    operator = scoring_setup["operator"]
    organizer = scoring_setup["organizer"]
    score_response = create_score_record(
        station.id,
        ScoreCreate(event_participant_id=registration.id, points=4),
        db_session,
    )

    with pytest.raises(HTTPException) as error:
        update_score(
            score_response["id"],
            ScoreUpdate(points=6, reason="Correction"),
            operator,
            db_session,
        )
    assert error.value.status_code == 403

    updated = update_score(
        score_response["id"],
        ScoreUpdate(points=8, reason="  Fixed a transcription error  "),
        organizer,
        db_session,
    )
    assert updated["points"] == 8
    assert updated["is_annulled"] is False
    audit = db_session.query(ScoreAudit).one()
    assert audit.action == "correction"
    assert audit.points_before == 4
    assert audit.points_after == 8
    assert audit.reason == "Fixed a transcription error"


def test_score_corrections_require_a_nonblank_reason():
    with pytest.raises(ValueError):
        ScoreUpdate(points=4, reason="  ")

    with pytest.raises(ValueError):
        ScoreAnnulment(reason="  ")


def test_score_history_is_system_admin_only(db_session, scoring_setup):
    with pytest.raises(HTTPException) as error:
        list_event_scores(
            scoring_setup["event"].id,
            scoring_setup["operator"],
            db_session,
        )

    assert error.value.status_code == 403


def test_system_admin_can_annul_score_and_audit_reason(
    db_session, scoring_setup
):
    station = scoring_setup["station"]
    registration = scoring_setup["registrations"][0]
    score = create_score_record(
        station.id,
        ScoreCreate(event_participant_id=registration.id, points=6),
        db_session,
    )

    annulled = annul_score(
        score["id"],
        ScoreAnnulment(reason="Participant was scored in error"),
        scoring_setup["organizer"],
        db_session,
    )

    assert annulled["is_annulled"] is True
    audit = db_session.query(ScoreAudit).one()
    assert audit.action == "annulment"
    assert audit.points_before == audit.points_after == 6
    assert audit.reason == "Participant was scored in error"

    lookup = lookup_participant_record(
        station.id,
        ParticipantLookup(registration_number="000001"),
        db_session,
    )
    assert lookup["already_scored"] is True
    assert lookup["score"]["is_annulled"] is True


def test_only_system_admin_can_annul_score_and_duplicate_annulment_is_rejected(
    db_session, scoring_setup
):
    station = scoring_setup["station"]
    score = create_score_record(
        station.id,
        ScoreCreate(
            event_participant_id=scoring_setup["registrations"][0].id,
            points=6,
        ),
        db_session,
    )
    request = ScoreAnnulment(reason="Duplicate scoring")

    with pytest.raises(HTTPException) as error:
        annul_score(score["id"], request, scoring_setup["operator"], db_session)
    assert error.value.status_code == 403

    annul_score(score["id"], request, scoring_setup["organizer"], db_session)
    with pytest.raises(HTTPException) as error:
        annul_score(score["id"], request, scoring_setup["organizer"], db_session)
    assert error.value.status_code == 409


def test_system_admin_can_read_event_score_history(
    db_session, scoring_setup
):
    station = scoring_setup["station"]
    score = create_score_record(
        station.id,
        ScoreCreate(
            event_participant_id=scoring_setup["registrations"][0].id,
            points=4,
        ),
        db_session,
    )
    update_score(
        score["id"],
        ScoreUpdate(points=6, reason="Correction"),
        scoring_setup["organizer"],
        db_session,
    )

    result = list_event_scores(
        scoring_setup["event"].id,
        scoring_setup["organizer"],
        db_session,
    )

    assert len(result) == 1
    assert result[0]["registration_number"] == "000001"
    assert result[0]["station_name"] == "Main"
    assert result[0]["points"] == 6
    assert result[0]["history"][0]["reason"] == "Correction"
    assert result[0]["history"][0]["changed_by"] == "Admin"


def test_public_leaderboard_includes_zero_scores_and_tied_places(
    db_session, scoring_setup
):
    station = scoring_setup["station"]
    registrations = scoring_setup["registrations"]
    operator = scoring_setup["operator"]
    for registration in registrations[:2]:
        create_score_record(
            station.id,
            ScoreCreate(event_participant_id=registration.id, points=6),
            db_session,
        )

    result = read_public_leaderboard(
        scoring_setup["event"].id,
        session=db_session,
    )
    participants = result["participants"]

    assert [row["registration_number"] for row in participants] == [
        "000001",
        "000002",
        "000003",
    ]
    assert [row["place"] for row in participants] == [1, 1, 3]
    assert [row["total_points"] for row in participants] == [6, 6, 0]
    assert [row["stations_completed"] for row in participants] == [1, 1, 0]
    assert all(row["stations_total"] == 2 for row in participants)
    assert set(participants[0]) == {
        "registration_number",
        "place",
        "total_points",
        "stations_completed",
        "stations_total",
        "stations",
    }
    assert participants[0]["stations"] == [
        {"station_id": station.id, "name": "Main", "points": 6, "score_max": 10},
        {
            "station_id": scoring_setup["another_station"].id,
            "name": "Side",
            "points": None,
            "score_max": 4,
        },
    ]
    assert "phone" not in participants[0]
    assert "workplace_or_study" not in participants[0]


def test_annulled_score_is_excluded_from_public_leaderboard(
    db_session, scoring_setup
):
    station = scoring_setup["station"]
    score = create_score_record(
        station.id,
        ScoreCreate(
            event_participant_id=scoring_setup["registrations"][0].id,
            points=6,
        ),
        db_session,
    )
    annul_score(
        score["id"],
        ScoreAnnulment(reason="Recorded against the wrong participant"),
        scoring_setup["organizer"],
        db_session,
    )

    result = read_public_leaderboard(
        scoring_setup["event"].id,
        session=db_session,
    )
    first = result["participants"][0]
    assert first["registration_number"] == "000001"
    assert first["total_points"] == 0
    assert first["stations_completed"] == 0
    assert first["stations"][0]["points"] is None


@pytest.mark.skipif(
    not os.environ.get("KERFUFFLE_TEST_POSTGRES_URL"),
    reason="Set KERFUFFLE_TEST_POSTGRES_URL to a disposable PostgreSQL test database",
)
def test_postgresql_concurrent_score_insert_is_unique():
    database_url = os.environ["KERFUFFLE_TEST_POSTGRES_URL"]
    schema_name = f"score_test_{uuid4().hex}"
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
            event_record = Event(name="Concurrent score", event_date=date(2026, 11, 18))
            person = Person(first_name="Concurrent", last_name="Participant")
            session.add_all([event_record, person])
            session.flush()
            station = Station(
                event_id=event_record.id,
                name="Single station",
                score_min=0,
                score_max=10,
                score_step=1,
            )
            session.add(station)
            session.flush()
            registration = EventParticipant(
                event_id=event_record.id,
                person_id=person.id,
                registration_number="000001",
            )
            session.add(registration)
            session.commit()
            station_id = station.id
            registration_id = registration.id

        barrier = Barrier(2)

        def submit_score(_: int) -> int:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    create_score_record(
                        station_id,
                        ScoreCreate(
                            event_participant_id=registration_id,
                            points=7,
                        ),
                        session,
                    )
                except HTTPException as error:
                    return error.status_code
                return 201

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit_score, range(2)))

        assert sorted(results) == [201, 409]
        with Session(engine) as session:
            score_count = session.scalar(
                select(func.count()).select_from(Score)
            )
            assert score_count == 1
            assert session.scalar(
                select(Score.points).where(
                    Score.event_participant_id == registration_id,
                    Score.station_id == station_id,
                )
            ) == 7
    finally:
        if engine is not None:
            engine.dispose()
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(
                f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'
            )
        admin_engine.dispose()


def test_public_leaderboard_supports_route_sheet_and_counts_off_route_scores(
    db_session, scoring_setup
):
    event_record = scoring_setup["event"]
    route_sheet = RouteSheet(event_id=event_record.id, name="North")
    db_session.add(route_sheet)
    db_session.flush()
    db_session.add(
        RouteSheetStation(
            route_sheet_id=route_sheet.id,
            event_id=event_record.id,
            station_id=scoring_setup["another_station"].id,
        )
    )
    registration = scoring_setup["registrations"][0]
    registration.route_sheet_id = route_sheet.id
    db_session.flush()
    create_score_record(
        scoring_setup["station"].id,
        ScoreCreate(event_participant_id=registration.id, points=6),
        db_session,
    )

    route_result = read_public_leaderboard(
        event_record.id,
        route_sheet_id=route_sheet.id,
        session=db_session,
    )
    all_result = read_public_leaderboard(event_record.id, session=db_session)

    assert [row["registration_number"] for row in route_result["participants"]] == ["000001"]
    assert route_result["participants"][0]["total_points"] == 6
    assert [row["registration_number"] for row in all_result["participants"]] == [
        "000001",
        "000002",
        "000003",
    ]
    assert all_result["participants"][0]["total_points"] == 6
    public_event = next(
        item for item in list_public_events(db_session) if item["id"] == event_record.id
    )
    assert public_event["route_sheets"] == [
        {"id": route_sheet.id, "name": "North"}
    ]

    with pytest.raises(HTTPException) as error:
        read_public_leaderboard(
            scoring_setup["other_event"].id,
            route_sheet_id=route_sheet.id,
            session=db_session,
        )
    assert error.value.status_code == 404


def test_public_leaderboard_returns_not_found_for_unknown_event(db_session):
    with pytest.raises(HTTPException) as error:
        read_public_leaderboard(999, session=db_session)

    assert error.value.status_code == 404
