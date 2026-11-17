"""Add local account credentials, sessions, invitations, and reset tokens.

Revision ID: 0006_local_auth
Revises: 0005_scoped_access_codes
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_local_auth"
down_revision = "0005_scoped_access_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT lower(email)
                  FROM users
                 WHERE email IS NOT NULL
                 GROUP BY lower(email)
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Duplicate emails differ only by case; resolve them before local-auth migration';
            END IF;
        END
        $$
        """
    )
    op.execute("ALTER TABLE users ALTER COLUMN auth_subject DROP NOT NULL")
    op.alter_column(
        "users",
        "auth_subject",
        new_column_name="legacy_identity_subject",
        existing_type=sa.Text(),
        existing_nullable=True,
    )
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "users_email_ci_unique",
        "users",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("csrf_token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("user_sessions_user_expiry_idx", "user_sessions", ["user_id", "expires_at"])
    op.create_table(
        "organizer_invitations",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("created_by_user_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("organizer_invitations_email_status_idx", "organizer_invitations", ["email", "expires_at"])
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("password_reset_user_expiry_idx", "password_reset_tokens", ["user_id", "expires_at"])
    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("ip_hash", sa.Text(), nullable=False),
        sa.Column("email_hash", sa.Text(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("auth_attempts_ip_time_idx", "auth_attempts", ["ip_hash", "created_at"])
    op.create_index("auth_attempts_email_time_idx", "auth_attempts", ["email_hash", "created_at"])

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kerfuffle_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON user_sessions, organizer_invitations, password_reset_tokens, auth_attempts
                    TO kerfuffle_app;
                GRANT USAGE, SELECT
                    ON SEQUENCE user_sessions_id_seq, organizer_invitations_id_seq,
                        password_reset_tokens_id_seq, auth_attempts_id_seq
                    TO kerfuffle_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE auth_attempts")
    op.execute("DROP TABLE password_reset_tokens")
    op.execute("DROP TABLE organizer_invitations")
    op.execute("DROP TABLE user_sessions")
    op.drop_index("users_email_ci_unique", table_name="users")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "password_hash")
    op.alter_column(
        "users",
        "legacy_identity_subject",
        new_column_name="auth_subject",
        existing_type=sa.Text(),
        existing_nullable=True,
    )
