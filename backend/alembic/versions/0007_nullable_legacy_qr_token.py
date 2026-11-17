"""Stop requiring the legacy QR token for new participant rows.

Revision ID: 0007_nullable_legacy_qr_token
Revises: 0006_local_auth
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_nullable_legacy_qr_token"
down_revision = "0006_local_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "event_participants",
        "qr_token",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    null_count = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM event_participants WHERE qr_token IS NULL"
        )
    ).scalar_one()
    if null_count:
        raise RuntimeError(
            "Cannot require legacy QR tokens: registrations created after "
            "0007 have no QR token."
        )

    op.alter_column(
        "event_participants",
        "qr_token",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
