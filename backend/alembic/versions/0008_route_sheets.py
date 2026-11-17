"""Add route sheets and registration assignments.

Revision ID: 0008_route_sheets
Revises: 0007_nullable_legacy_qr_token
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_route_sheets"
down_revision = "0007_nullable_legacy_qr_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "route_sheets",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "event_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("capacity", sa.Integer()),
        sa.UniqueConstraint("id", "event_id", name="route_sheets_id_event_unique"),
        sa.UniqueConstraint(
            "event_id", "name", name="route_sheets_name_per_event_unique"
        ),
        sa.CheckConstraint("btrim(name) <> ''", name="route_sheets_name_not_empty"),
        sa.CheckConstraint(
            "capacity IS NULL OR capacity > 0",
            name="route_sheets_capacity_positive",
        ),
    )
    op.create_table(
        "route_sheet_stations",
        sa.Column(
            "route_sheet_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "station_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("route_sheet_id", "station_id"),
        sa.ForeignKeyConstraint(
            ["route_sheet_id", "event_id"],
            ["route_sheets.id", "route_sheets.event_id"],
            name="route_sheet_stations_sheet_event_fk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["station_id", "event_id"],
            ["stations.id", "stations.event_id"],
            name="route_sheet_stations_station_event_fk",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "route_sheet_stations_event_station_idx",
        "route_sheet_stations",
        ["event_id", "station_id"],
    )
    op.add_column(
        "event_participants",
        sa.Column(
            "route_sheet_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "event_participants_route_sheet_event_fk",
        "event_participants",
        "route_sheets",
        ["route_sheet_id", "event_id"],
        ["id", "event_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "event_participants_route_sheet_idx",
        "event_participants",
        ["route_sheet_id"],
    )

    op.execute(
        """
        CREATE FUNCTION prevent_route_sheet_station_change_after_use()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
            target_route_sheet_id BIGINT;
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION
                    'Route sheet station entries cannot be updated'
                    USING ERRCODE = '23514';
            END IF;

            IF TG_OP = 'DELETE' THEN
                target_route_sheet_id := OLD.route_sheet_id;
            ELSE
                target_route_sheet_id := NEW.route_sheet_id;
            END IF;

            PERFORM 1
              FROM route_sheets
             WHERE id = target_route_sheet_id
             FOR UPDATE;

            IF EXISTS (
                SELECT 1
                  FROM event_participants
                 WHERE route_sheet_id = target_route_sheet_id
            ) THEN
                RAISE EXCEPTION
                    'Route sheet stations cannot change after participant assignment'
                    USING ERRCODE = '23514';
            END IF;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER route_sheet_stations_immutable_after_assignment
        BEFORE INSERT OR UPDATE OR DELETE ON route_sheet_stations
        FOR EACH ROW
        EXECUTE FUNCTION prevent_route_sheet_station_change_after_use()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_score_route_sheet_station()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM event_participants AS participant
                 WHERE participant.id = NEW.event_participant_id
                   AND participant.route_sheet_id IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1
                         FROM route_sheet_stations AS route_station
                        WHERE route_station.route_sheet_id = participant.route_sheet_id
                          AND route_station.station_id = NEW.station_id
                   )
            ) THEN
                RAISE EXCEPTION
                    'Station is not included in the participant route sheet'
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
        FOR EACH ROW
        EXECUTE FUNCTION validate_score_route_sheet_station()
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kerfuffle_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON route_sheets, route_sheet_stations
                    TO kerfuffle_app;
                GRANT USAGE, SELECT ON SEQUENCE route_sheets_id_seq
                    TO kerfuffle_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    route_count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM route_sheets")
    ).scalar_one()
    assignment_count = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM event_participants WHERE route_sheet_id IS NOT NULL"
        )
    ).scalar_one()
    if route_count or assignment_count:
        raise RuntimeError(
            "Cannot remove route sheets while route definitions or assignments exist."
        )

    op.execute("DROP TRIGGER scores_route_sheet_station ON scores")
    op.execute("DROP FUNCTION validate_score_route_sheet_station()")
    op.execute(
        "DROP TRIGGER route_sheet_stations_immutable_after_assignment "
        "ON route_sheet_stations"
    )
    op.execute("DROP FUNCTION prevent_route_sheet_station_change_after_use()")
    op.drop_index(
        "event_participants_route_sheet_idx",
        table_name="event_participants",
    )
    op.drop_constraint(
        "event_participants_route_sheet_event_fk",
        "event_participants",
        type_="foreignkey",
    )
    op.drop_column("event_participants", "route_sheet_id")
    op.drop_index(
        "route_sheet_stations_event_station_idx",
        table_name="route_sheet_stations",
    )
    op.drop_table("route_sheet_stations")
    op.drop_table("route_sheets")
