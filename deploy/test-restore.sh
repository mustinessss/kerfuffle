#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/kerfuffle-YYYYMMDDTHHMMSSZ.sql.gz" >&2
  exit 1
fi

BACKUP="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(-f "$ROOT/deploy/compose.production.yaml" --env-file "$ROOT/deploy/.env.production")
TEST_DB="kerfuffle_restore_test_$(date -u +%Y%m%dT%H%M%SZ)_$$"
TEST_DB_CREATED=0

cleanup_test_db() {
  local exit_code=$?
  if [[ "$TEST_DB_CREATED" -eq 1 ]]; then
    if ! docker compose "${COMPOSE[@]}" exec -T db \
      env PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -d postgres \
      -v ON_ERROR_STOP=1 -c "DROP DATABASE \"$TEST_DB\";"; then
      echo "Could not remove temporary restore database $TEST_DB." >&2
      exit_code=1
    fi
  fi
  return "$exit_code"
}
trap cleanup_test_db EXIT

test -s "$BACKUP"
gzip -t "$BACKUP"
if [[ -f "$BACKUP.sha256" ]]; then
  (cd "$(dirname "$BACKUP")" && sha256sum -c "$(basename "$BACKUP").sha256")
fi

set -a
source "$ROOT/deploy/.env.production"
set +a

docker compose "${COMPOSE[@]}" exec -T db \
  env PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -d postgres \
  -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$TEST_DB\";"
TEST_DB_CREATED=1

gzip -dc "$BACKUP" | docker compose "${COMPOSE[@]}" exec -T db \
  env PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -d "$TEST_DB" -v ON_ERROR_STOP=1

docker compose "${COMPOSE[@]}" exec -T db \
  env PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -d "$TEST_DB" \
  -v ON_ERROR_STOP=1 \
  -c "SELECT version_num FROM alembic_version;" \
  -c "SELECT (SELECT count(*) FROM events) AS events, (SELECT count(*) FROM event_participants) AS registrations, (SELECT count(*) FROM stations) AS stations, (SELECT count(*) FROM scores) AS scores;"

echo "Backup restoration to a separate test database completed successfully."
