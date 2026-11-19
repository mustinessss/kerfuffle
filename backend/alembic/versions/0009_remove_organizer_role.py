"""Replace organizer access with system-admin and station-scoped access.

Revision ID: 0009_remove_organizer_role
Revises: 0008_route_sheets
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_remove_organizer_role"
down_revision = "0008_route_sheets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE legacy_event_access (
            id BIGINT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            event_id BIGINT NOT NULL,
            role TEXT NOT NULL,
            station_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO legacy_event_access
        SELECT id, user_id, event_id, role, station_id, created_at
          FROM event_access
         WHERE role <> 'station_operator'
        """
    )
    op.execute("DELETE FROM event_access WHERE role <> 'station_operator'")
    op.execute(
        "ALTER TABLE event_access DROP CONSTRAINT access_station_required_for_operator"
    )
    op.execute("ALTER TABLE event_access DROP CONSTRAINT event_access_valid_role")
    op.execute(
        """
        ALTER TABLE event_access
        ADD CONSTRAINT access_station_required_for_operator
        CHECK (role = 'station_operator' AND station_id IS NOT NULL)
        """
    )
    op.execute(
        """
        ALTER TABLE event_access
        ADD CONSTRAINT event_access_valid_role
        CHECK (role = 'station_operator')
        """
    )

    op.execute(
        """
        CREATE TABLE legacy_access_codes AS
        SELECT * FROM access_codes WHERE role = 'registrar'
        """
    )
    op.execute(
        """
        CREATE TABLE legacy_access_sessions AS
        SELECT sessions.*
          FROM access_sessions AS sessions
          JOIN legacy_access_codes AS codes ON codes.id = sessions.access_code_id
        """
    )
    op.execute(
        """
        DELETE FROM access_sessions
         WHERE access_code_id IN (SELECT id FROM legacy_access_codes)
        """
    )
    op.execute("DELETE FROM access_codes WHERE role = 'registrar'")
    op.execute("ALTER TABLE access_codes DROP CONSTRAINT access_codes_valid_scope")
    op.execute(
        """
        ALTER TABLE access_codes
        ADD CONSTRAINT access_codes_valid_scope
        CHECK (role = 'station_operator' AND station_id IS NOT NULL)
        """
    )

    op.execute(
        """
        CREATE TABLE legacy_user_organizer_flags (
            user_id BIGINT PRIMARY KEY,
            is_organizer BOOLEAN NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO legacy_user_organizer_flags (user_id, is_organizer)
        SELECT id, is_organizer FROM users
        """
    )
    op.drop_column("users", "is_organizer")

    op.execute(
        "ALTER TABLE organizer_invitations RENAME TO account_invitations"
    )
    op.execute(
        "ALTER INDEX organizer_invitations_email_status_idx "
        "RENAME TO account_invitations_email_status_idx"
    )

    op.execute("DROP TRIGGER scores_route_sheet_station ON scores")
    op.execute("DROP FUNCTION validate_score_route_sheet_station()")
    op.execute(
        "DROP TRIGGER route_sheet_stations_immutable_after_assignment "
        "ON route_sheet_stations"
    )
    op.execute("DROP FUNCTION prevent_route_sheet_station_change_after_use()")

    op.create_check_constraint(
        "event_participants_registration_number_format",
        "event_participants",
        "registration_number ~ '^[0-9]{6}$'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "event_participants_registration_number_format",
        "event_participants",
        type_="check",
    )
    op.execute(
        "ALTER INDEX account_invitations_email_status_idx "
        "RENAME TO organizer_invitations_email_status_idx"
    )
    op.execute(
        "ALTER TABLE account_invitations RENAME TO organizer_invitations"
    )

    op.execute(
        """
        CREATE FUNCTION prevent_route_sheet_station_change_after_use()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        DECLARE target_route_sheet_id BIGINT;
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION 'Route sheet station entries cannot be updated'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'DELETE' THEN
                target_route_sheet_id := OLD.route_sheet_id;
            ELSE
                target_route_sheet_id := NEW.route_sheet_id;
            END IF;
            PERFORM 1 FROM route_sheets WHERE id = target_route_sheet_id FOR UPDATE;
            IF EXISTS (
                SELECT 1 FROM event_participants
                 WHERE route_sheet_id = target_route_sheet_id
            ) THEN
                RAISE EXCEPTION 'Route sheet stations cannot change after participant assignment'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER route_sheet_stations_immutable_after_assignment
        BEFORE INSERT OR UPDATE OR DELETE ON route_sheet_stations
        FOR EACH ROW EXECUTE FUNCTION prevent_route_sheet_station_change_after_use()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_score_route_sheet_station()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM event_participants AS participant
                 WHERE participant.id = NEW.event_participant_id
                   AND participant.route_sheet_id IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM route_sheet_stations AS route_station
                        WHERE route_station.route_sheet_id = participant.route_sheet_id
                          AND route_station.station_id = NEW.station_id
                   )
            ) THEN
                RAISE EXCEPTION 'Station is not included in the participant route sheet'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER scores_route_sheet_station
        BEFORE INSERT OR UPDATE ON scores
        FOR EACH ROW EXECUTE FUNCTION validate_score_route_sheet_station()
        """
    )

    op.add_column(
        "users",
        sa.Column(
            "is_organizer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(
        """
        UPDATE users
           SET is_organizer = legacy_user_organizer_flags.is_organizer
          FROM legacy_user_organizer_flags
         WHERE users.id = legacy_user_organizer_flags.user_id
        """
    )
    op.execute("DROP TABLE legacy_user_organizer_flags")

    op.execute("ALTER TABLE event_access DROP CONSTRAINT event_access_valid_role")
    op.execute(
        "ALTER TABLE event_access DROP CONSTRAINT access_station_required_for_operator"
    )
    op.execute(
        """
        ALTER TABLE event_access
        ADD CONSTRAINT access_station_required_for_operator
        CHECK (
            (role = 'station_operator' AND station_id IS NOT NULL)
            OR (role IN ('organizer', 'registrar') AND station_id IS NULL)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE event_access
        ADD CONSTRAINT event_access_valid_role
        CHECK (role IN ('organizer', 'registrar', 'station_operator'))
        """
    )
    op.execute(
        """
        INSERT INTO event_access (id, user_id, event_id, role, station_id, created_at)
        OVERRIDING SYSTEM VALUE
        SELECT id, user_id, event_id, role, station_id, created_at
          FROM legacy_event_access
        """
    )
    op.execute("DROP TABLE legacy_event_access")

    op.execute("ALTER TABLE access_codes DROP CONSTRAINT access_codes_valid_scope")
    op.execute(
        """
        ALTER TABLE access_codes
        ADD CONSTRAINT access_codes_valid_scope CHECK (
            (role = 'registrar' AND station_id IS NULL)
            OR (role = 'station_operator' AND station_id IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        INSERT INTO access_codes OVERRIDING SYSTEM VALUE
        SELECT * FROM legacy_access_codes
        """
    )
    op.execute(
        """
        INSERT INTO access_sessions OVERRIDING SYSTEM VALUE
        SELECT * FROM legacy_access_sessions
        """
    )
    op.execute("DROP TABLE legacy_access_sessions")
    op.execute("DROP TABLE legacy_access_codes")
