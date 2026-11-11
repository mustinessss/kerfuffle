from sqlalchemy import create_engine, event, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db import models
from app.db.session import Base


def test_all_design_document_tables_have_models():
    assert set(Base.metadata.tables) == {
        "people",
        "events",
        "users",
        "stations",
        "event_participants",
        "event_access",
        "scores",
    }


def test_registration_and_score_constraints_are_present():
    registrations = models.EventParticipant.__table__
    scores = models.Score.__table__
    stations = models.Station.__table__

    assert "one_registration_per_person_event" in {
        constraint.name for constraint in registrations.constraints
    }
    assert "one_score_per_participant_station" in {
        constraint.name for constraint in scores.constraints
    }
    assert "stations_valid_score_scale" in {
        constraint.name for constraint in stations.constraints
    }


def test_station_operator_access_is_unique_per_station():
    indexes = {
        index.name: index
        for index in models.EventAccess.__table__.indexes
    }

    assert indexes["event_access_operator_station_unique"].unique
    assert str(
        indexes["event_access_operator_station_unique"]
        .dialect_options["postgresql"]["where"]
    ) == "role = 'station_operator'"


def test_postgresql_primary_keys_use_identity_columns():
    ddl = str(
        CreateTable(models.Person.__table__).compile(dialect=postgresql.dialect())
    )

    assert "BIGINT GENERATED ALWAYS AS IDENTITY" in ddl


def test_metadata_can_create_all_seven_tables():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.create_function(
            "btrim", 1, lambda value: None if value is None else value.strip()
        ),
    )
    Base.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables)

    engine.dispose()
