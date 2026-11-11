"""Use six-digit participant registration numbers.

Revision ID: 0002_six_digit_ids
Revises: 0001_initial
"""
from alembic import op
from sqlalchemy import text


revision = "0002_six_digit_ids"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    invalid_numbers = connection.scalar(
        text(
            """
            SELECT count(*)
            FROM event_participants
            WHERE registration_number !~ '^[0-9]{1,6}$'
            """
        )
    )
    if invalid_numbers:
        raise RuntimeError(
            "Cannot migrate registration numbers: expected one to six digits"
        )

    duplicate_numbers = connection.scalar(
        text(
            """
            SELECT count(*)
            FROM (
                SELECT event_id, lpad(registration_number, 6, '0')
                FROM event_participants
                GROUP BY event_id, lpad(registration_number, 6, '0')
                HAVING count(*) > 1
            ) AS duplicate_registrations
            """
        )
    )
    if duplicate_numbers:
        raise RuntimeError(
            "Cannot migrate registration numbers: padding would create duplicates"
        )

    op.execute(
        """
        UPDATE event_participants
        SET registration_number = lpad(registration_number, 6, '0')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE event_participants
        SET registration_number = lpad(
            ltrim(registration_number, '0'),
            greatest(4, length(ltrim(registration_number, '0'))),
            '0'
        )
        """
    )
