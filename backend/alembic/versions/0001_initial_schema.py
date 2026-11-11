"""Create the initial Kerfuffle schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE people (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            birth_date DATE,
            workplace_or_study TEXT,
            phone TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT people_first_name_not_empty CHECK (btrim(first_name) <> ''),
            CONSTRAINT people_last_name_not_empty CHECK (btrim(last_name) <> '')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE events (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name TEXT NOT NULL,
            event_date DATE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT events_name_not_empty CHECK (btrim(name) <> '')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE users (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            auth_subject TEXT NOT NULL UNIQUE,
            email TEXT,
            display_name TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_system_admin BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT users_display_name_not_empty CHECK (btrim(display_name) <> '')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE stations (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            event_id BIGINT NOT NULL
                REFERENCES events(id) ON DELETE RESTRICT,
            name TEXT NOT NULL,
            score_min INTEGER NOT NULL,
            score_max INTEGER NOT NULL,
            score_step INTEGER NOT NULL,
            CONSTRAINT stations_id_event_unique UNIQUE (id, event_id),
            CONSTRAINT stations_name_per_event_unique UNIQUE (event_id, name),
            CONSTRAINT stations_name_not_empty CHECK (btrim(name) <> ''),
            CONSTRAINT stations_valid_score_scale CHECK (
                score_min >= 0
                AND score_max >= score_min
                AND score_step > 0
                AND (score_max - score_min) % score_step = 0
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE event_participants (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            event_id BIGINT NOT NULL
                REFERENCES events(id) ON DELETE RESTRICT,
            person_id BIGINT NOT NULL
                REFERENCES people(id) ON DELETE RESTRICT,
            registration_number TEXT NOT NULL,
            qr_token UUID NOT NULL UNIQUE,
            registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT one_registration_per_person_event
                UNIQUE (person_id, event_id),
            CONSTRAINT registration_number_per_event_unique
                UNIQUE (event_id, registration_number),
            CONSTRAINT event_participants_registration_number_not_empty
                CHECK (btrim(registration_number) <> '')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE event_access (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id BIGINT NOT NULL
                REFERENCES users(id) ON DELETE RESTRICT,
            event_id BIGINT NOT NULL
                REFERENCES events(id) ON DELETE RESTRICT,
            role TEXT NOT NULL,
            station_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT access_station_required_for_operator CHECK (
                (role = 'station_operator' AND station_id IS NOT NULL)
                OR
                (role IN ('organizer', 'registrar') AND station_id IS NULL)
            ),
            CONSTRAINT access_station_must_belong_to_event
                FOREIGN KEY (station_id, event_id)
                REFERENCES stations (id, event_id) ON DELETE RESTRICT,
            CONSTRAINT event_access_valid_role
                CHECK (role IN ('organizer', 'registrar', 'station_operator'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE scores (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            event_participant_id BIGINT NOT NULL
                REFERENCES event_participants(id) ON DELETE RESTRICT,
            station_id BIGINT NOT NULL
                REFERENCES stations(id) ON DELETE RESTRICT,
            points INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT one_score_per_participant_station
                UNIQUE (event_participant_id, station_id),
            CONSTRAINT scores_points_non_negative CHECK (points >= 0)
        )
        """
    )

    op.execute(
        "CREATE INDEX event_participants_event_idx "
        "ON event_participants (event_id, registered_at)"
    )
    op.execute("CREATE INDEX scores_station_idx ON scores (station_id)")
    op.execute("CREATE INDEX event_access_user_idx ON event_access (user_id, event_id)")
    op.execute(
        "CREATE UNIQUE INDEX event_access_event_role_unique "
        "ON event_access (event_id, user_id, role) WHERE station_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX event_access_operator_station_unique "
        "ON event_access (event_id, user_id, station_id) "
        "WHERE role = 'station_operator'"
    )

    op.execute(
        """
        CREATE FUNCTION validate_score_before_write()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
            participant_event_id BIGINT;
            station_event_id BIGINT;
            station_score_min INTEGER;
            station_score_max INTEGER;
            station_score_step INTEGER;
        BEGIN
            SELECT ep.event_id
              INTO participant_event_id
              FROM event_participants AS ep
             WHERE ep.id = NEW.event_participant_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Registration does not exist'
                    USING ERRCODE = '23503';
            END IF;

            SELECT s.event_id, s.score_min, s.score_max, s.score_step
              INTO station_event_id, station_score_min,
                   station_score_max, station_score_step
              FROM stations AS s
             WHERE s.id = NEW.station_id
             FOR UPDATE;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Station does not exist'
                    USING ERRCODE = '23503';
            END IF;

            IF participant_event_id <> station_event_id THEN
                RAISE EXCEPTION
                    'Participant and station must belong to the same event'
                    USING ERRCODE = '23514';
            END IF;

            IF NEW.points < station_score_min
               OR NEW.points > station_score_max
               OR (NEW.points - station_score_min) % station_score_step <> 0 THEN
                RAISE EXCEPTION 'Points do not match station scoring scale'
                    USING ERRCODE = '23514';
            END IF;

            IF TG_OP = 'UPDATE' THEN
                NEW.updated_at := now();
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER scores_validate_before_write
        BEFORE INSERT OR UPDATE ON scores
        FOR EACH ROW
        EXECUTE FUNCTION validate_score_before_write()
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_station_scale_change_after_scores()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.score_min IS DISTINCT FROM OLD.score_min
               OR NEW.score_max IS DISTINCT FROM OLD.score_max
               OR NEW.score_step IS DISTINCT FROM OLD.score_step THEN
                IF EXISTS (
                    SELECT 1
                      FROM scores
                     WHERE station_id = OLD.id
                ) THEN
                    RAISE EXCEPTION
                        'Station scoring scale cannot be changed after scores exist'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER stations_prevent_scale_change
        BEFORE UPDATE OF score_min, score_max, score_step ON stations
        FOR EACH ROW
        EXECUTE FUNCTION prevent_station_scale_change_after_scores()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER stations_prevent_scale_change ON stations")
    op.execute("DROP TRIGGER scores_validate_before_write ON scores")
    op.execute("DROP FUNCTION prevent_station_scale_change_after_scores()")
    op.execute("DROP FUNCTION validate_score_before_write()")
    op.drop_table("scores")
    op.drop_table("event_access")
    op.drop_table("event_participants")
    op.drop_table("stations")
    op.drop_table("users")
    op.drop_table("events")
    op.drop_table("people")
