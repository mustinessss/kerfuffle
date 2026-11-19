"""Allow event-scoped registrar access codes.

Revision ID: 0011_registrar_access_codes
Revises: 0010_add_registrar_role
"""

from alembic import op


revision = "0011_registrar_access_codes"
down_revision = "0010_add_registrar_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE access_codes DROP CONSTRAINT access_codes_valid_scope")
    op.execute(
        """
        ALTER TABLE access_codes
        ADD CONSTRAINT access_codes_valid_scope
        CHECK (
            (role = 'station_operator' AND station_id IS NOT NULL)
            OR (role = 'registrar' AND station_id IS NULL)
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM access_codes WHERE role = 'registrar'
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade while registrar access codes exist';
            END IF;
        END
        $$;
        """
    )
    op.execute("ALTER TABLE access_codes DROP CONSTRAINT access_codes_valid_scope")
    op.execute(
        """
        ALTER TABLE access_codes
        ADD CONSTRAINT access_codes_valid_scope
        CHECK (role = 'station_operator' AND station_id IS NOT NULL)
        """
    )
