#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(-f "$ROOT/deploy/compose.production.yaml" --env-file "$ROOT/deploy/.env.production")
BACKUP_DIR="${KERFUFFLE_BACKUP_DIR:-$ROOT/deploy/backups}"
mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP_FILE="$(mktemp "$BACKUP_DIR/kerfuffle-${STAMP}.XXXXXX.sql.gz.partial")"
FILE="${TMP_FILE%.partial}"
trap 'rm -f -- "$TMP_FILE"' EXIT

set -a
source "$ROOT/deploy/.env.production"
set +a

docker compose "${COMPOSE[@]}" exec -T db \
  env PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  --username=postgres --dbname=kerfuffle --format=plain --no-owner --no-acl \
  | gzip -9 > "$TMP_FILE"

test -s "$TMP_FILE"
gzip -t "$TMP_FILE"
mv -- "$TMP_FILE" "$FILE"
(
  cd "$BACKUP_DIR"
  sha256sum "$(basename "$FILE")" > "$(basename "$FILE").sha256"
)
chmod 0600 "$FILE" "$FILE.sha256"
trap - EXIT
echo "Backup created and verified: $FILE"
echo "Checksum: $FILE.sha256"
