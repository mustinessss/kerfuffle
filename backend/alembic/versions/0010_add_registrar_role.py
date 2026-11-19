"""Add registrar role scoped to an event.

Revision ID: 0010_add_registrar_role
Revises: 0009_remove_organizer_role
"""

revision = "0010_add_registrar_role"
down_revision = "0009_remove_organizer_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op

    op.execute(
        "ALTER TABLE event_access "
        "DROP CONSTRAINT access_station_required_for_operator"
    )
    op.execute(
        "ALTER TABLE event_access DROP CONSTRAINT event_access_valid_role"
    )
    op.execute(
        """
        ALTER TABLE event_access
        ADD CONSTRAINT access_station_required_for_scoped_role
        CHECK (
            (role = 'station_operator' AND station_id IS NOT NULL)
            OR (role = 'registrar' AND station_id IS NULL)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE event_access
        ADD CONSTRAINT event_access_valid_role
        CHECK (role IN ('station_operator', 'registrar'))
        """
    )


def downgrade() -> None:
    from alembic import op

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM event_access WHERE role = 'registrar'
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade while registrar assignments exist';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        "ALTER TABLE event_access "
        "DROP CONSTRAINT access_station_required_for_scoped_role"
    )
    op.execute(
        "ALTER TABLE event_access DROP CONSTRAINT event_access_valid_role"
    )
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
