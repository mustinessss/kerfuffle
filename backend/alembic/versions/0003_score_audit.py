"""Add organizer score correction and annulment audit history.

Revision ID: 0003_score_audit
Revises: 0002_six_digit_ids
"""
from alembic import op


revision = "0003_score_audit"
down_revision = "0002_six_digit_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scores ADD COLUMN is_annulled BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        """
        CREATE TABLE score_audit (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            score_id BIGINT NOT NULL
                REFERENCES scores(id) ON DELETE RESTRICT,
            changed_by_user_id BIGINT NOT NULL
                REFERENCES users(id) ON DELETE RESTRICT,
            action TEXT NOT NULL,
            points_before INTEGER NOT NULL,
            points_after INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT score_audit_valid_action
                CHECK (action IN ('correction', 'annulment')),
            CONSTRAINT score_audit_reason_not_empty
                CHECK (btrim(reason) <> '')
        )
        """
    )
    op.execute(
        "CREATE INDEX score_audit_score_created_idx "
        "ON score_audit (score_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE score_audit")
    op.execute("ALTER TABLE scores DROP COLUMN is_annulled")
