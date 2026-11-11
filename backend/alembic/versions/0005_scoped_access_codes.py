"""Add organizer-managed registration and station access codes.

Revision ID: 0005_scoped_access_codes
Revises: 0004_immutable_score_audit
"""
from alembic import op


revision = "0005_scoped_access_codes"
down_revision = "0004_immutable_score_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN is_organizer BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        """
        CREATE TABLE access_codes (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            event_id BIGINT NOT NULL
                REFERENCES events(id) ON DELETE RESTRICT,
            station_id BIGINT,
            created_by_user_id BIGINT NOT NULL
                REFERENCES users(id) ON DELETE RESTRICT,
            role TEXT NOT NULL,
            label TEXT NOT NULL,
            secret_hash TEXT NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at TIMESTAMPTZ,
            CONSTRAINT access_codes_valid_scope CHECK (
                (role = 'registrar' AND station_id IS NULL)
                OR (role = 'station_operator' AND station_id IS NOT NULL)
            ),
            CONSTRAINT access_codes_station_must_belong_to_event
                FOREIGN KEY (station_id, event_id)
                REFERENCES stations (id, event_id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX access_codes_event_idx ON access_codes (event_id, created_at)"
    )
    op.execute(
        """
        CREATE TABLE access_sessions (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            access_code_id BIGINT NOT NULL
                REFERENCES access_codes(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE access_code_attempts (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            ip_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX access_code_attempts_ip_time_idx "
        "ON access_code_attempts (ip_hash, created_at)"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kerfuffle_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON access_codes, access_sessions, access_code_attempts
                    TO kerfuffle_app;
                GRANT USAGE, SELECT
                    ON SEQUENCE access_codes_id_seq, access_sessions_id_seq,
                        access_code_attempts_id_seq
                    TO kerfuffle_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE access_code_attempts")
    op.execute("DROP TABLE access_sessions")
    op.execute("DROP TABLE access_codes")
    op.execute("ALTER TABLE users DROP COLUMN is_organizer")
