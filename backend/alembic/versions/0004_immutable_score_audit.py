"""Prevent score audit records from being changed or removed.

Revision ID: 0004_immutable_score_audit
Revises: 0003_score_audit
"""
from alembic import op


revision = "0004_immutable_score_audit"
down_revision = "0003_score_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION prevent_score_audit_mutation()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'score audit records are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER score_audit_immutable
        BEFORE UPDATE OR DELETE ON score_audit
        FOR EACH ROW EXECUTE FUNCTION prevent_score_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER score_audit_immutable ON score_audit")
    op.execute("DROP FUNCTION prevent_score_audit_mutation()")
