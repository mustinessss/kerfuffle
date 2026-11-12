\getenv app_db_password APP_DB_PASSWORD
CREATE ROLE kerfuffle_app LOGIN PASSWORD :'app_db_password';
\i /opt/kerfuffle/app_role.sql
