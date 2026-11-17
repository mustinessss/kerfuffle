#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(-f "$ROOT/deploy/compose.production.yaml" --env-file "$ROOT/deploy/.env.production")
BACKUP_DIR="${KERFUFFLE_BACKUP_DIR:-$ROOT/deploy/backups}"
mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$BACKUP_DIR/kerfuffle-${STAMP}.sql.gz"

set -a
source "$ROOT/deploy/.env.production"
set +a

docker compose "${COMPOSE[@]}" exec -T db \
  env PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  --username=postgres --dbname=kerfuffle --format=plain --no-owner --no-acl \
  | gzip -9 > "$FILE"

test -s "$FILE"
gzip -t "$FILE"
echo "Backup created and verified: $FILE"
