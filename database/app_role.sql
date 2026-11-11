-- Run as the database owner/administrator against the kerfuffle database.
-- Set a strong password separately with: \password kerfuffle_app
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_roles
         WHERE rolname = 'kerfuffle_app'
    ) THEN
        CREATE ROLE kerfuffle_app LOGIN;
    END IF;
END;
$$;

GRANT CONNECT ON DATABASE kerfuffle TO kerfuffle_app;
GRANT USAGE ON SCHEMA public TO kerfuffle_app;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO kerfuffle_app;
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public TO kerfuffle_app;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO kerfuffle_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO kerfuffle_app;
