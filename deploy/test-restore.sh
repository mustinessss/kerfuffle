#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/kerfuffle-YYYYMMDDTHHMMSSZ.sql.gz" >&2
  exit 1
fi

BACKUP="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(-f "$ROOT/deploy/compose.production.yaml" --env-file "$ROOT/deploy/.env.production")
TEST_DB="kerfuffle_restore_test"

test -s "$BACKUP"
gzip -t "$BACKUP"

set -a
source "$ROOT/deploy/.env.production"
set +a

docker compose "${COMPOSE[@]}" exec -T db \
  env PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -d postgres \
  -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $TEST_DB;" \
  -c "CREATE DATABASE $TEST_DB;"

gzip -dc "$BACKUP" | docker compose "${COMPOSE[@]}" exec -T db \
  env PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -d "$TEST_DB" -v ON_ERROR_STOP=1

docker compose "${COMPOSE[@]}" exec -T db \
  env PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -d "$TEST_DB" \
  -v ON_ERROR_STOP=1 -c "SELECT count(*) AS restored_tables FROM pg_tables WHERE schemaname='public';"

docker compose "${COMPOSE[@]}" exec -T db \
  env PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -d postgres \
  -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $TEST_DB;"

echo "Backup restoration to a separate test database completed successfully."
