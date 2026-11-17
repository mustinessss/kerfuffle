#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:16-alpine}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "OpenSSL is required." >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to determine the PostgreSQL image UID/GID." >&2
  exit 1
fi
if [[ $EUID -ne 0 ]]; then
  echo "Run this script with sudo so the PostgreSQL server key can be assigned to the container user." >&2
  exit 1
fi

# Resolve the actual UID/GID from the exact image used by Compose. Alpine and
# Debian variants do not necessarily use the same postgres UID/GID.
read -r POSTGRES_UID POSTGRES_GID < <(
  docker run --rm --entrypoint sh "$POSTGRES_IMAGE" \
    -c 'printf "%s %s\n" "$(id -u postgres)" "$(id -g postgres)"'
)
if [[ ! "$POSTGRES_UID" =~ ^[0-9]+$ || ! "$POSTGRES_GID" =~ ^[0-9]+$ ]]; then
  echo "Could not determine postgres UID/GID from $POSTGRES_IMAGE." >&2
  exit 1
fi

CONFIG_FILE="$(mktemp)"
trap 'rm -f "$CONFIG_FILE"' EXIT
cat > "$CONFIG_FILE" <<'EOF'
[req]
distinguished_name = dn
req_extensions = v3_req
prompt = no

[dn]
CN = db

[v3_req]
subjectAltName = @alt_names
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = db
EOF

openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
  -keyout ca.key -out ca.crt \
  -subj "/CN=Kerfuffle PostgreSQL CA" >/dev/null 2>&1
openssl req -new -nodes -newkey rsa:2048 \
  -keyout server.key -out server.csr \
  -config "$CONFIG_FILE" >/dev/null 2>&1
openssl x509 -req -days 3650 -in server.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -extfile "$CONFIG_FILE" -extensions v3_req >/dev/null 2>&1

# The CA private key is only used on the host and must remain owned by the
# operator. PostgreSQL itself needs read access to server.key after dropping
# root privileges inside the official container entrypoint.
chmod 0600 ca.key server.key
chmod 0644 ca.crt server.crt pg_hba.conf
chown "${POSTGRES_UID}:${POSTGRES_GID}" server.key
rm -f server.csr ca.srl

echo "Generated PostgreSQL TLS files in $(pwd)"
echo "PostgreSQL image: $POSTGRES_IMAGE (UID:GID ${POSTGRES_UID}:${POSTGRES_GID})"
echo "Keep ca.key private and store it outside the repository."
