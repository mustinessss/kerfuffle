"""Store access-code values encrypted for administrator display.

Revision ID: 0012_encrypt_access_code_values
Revises: 0011_registrar_access_codes
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_encrypt_access_code_values"
down_revision = "0011_registrar_access_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("access_codes", sa.Column("encrypted_code", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("access_codes", "encrypted_code")
