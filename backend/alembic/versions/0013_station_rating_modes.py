"""Add station rating modes.

Revision ID: 0013_station_rating_modes
Revises: 0012_encrypt_access_code_values
"""
from alembic import op
import sqlalchemy as sa


revision = "0013_station_rating_modes"
down_revision = "0012_encrypt_access_code_values"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stations",
        sa.Column(
            "rating_mode",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'main'"),
        ),
    )
    op.create_check_constraint(
        "stations_valid_rating_mode",
        "stations",
        "rating_mode IN ('main', 'separate')",
    )


def downgrade() -> None:
    separate_count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM stations WHERE rating_mode = 'separate'")
    ).scalar_one()
    if separate_count:
        raise RuntimeError(
            "Cannot drop station rating modes while separate ratings are configured."
        )
    op.drop_constraint(
        "stations_valid_rating_mode",
        "stations",
        type_="check",
    )
    op.drop_column("stations", "rating_mode")
