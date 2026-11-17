#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v openssl >/dev/null 2>&1; then
  echo "OpenSSL is required." >&2
  exit 1
fi

cat > openssl-server.cnf <<'EOF'
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
  -config openssl-server.cnf >/dev/null 2>&1
openssl x509 -req -days 3650 -in server.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -extfile openssl-server.cnf -extensions v3_req >/dev/null 2>&1

chmod 0600 ca.key server.key
chmod 0644 ca.crt server.crt pg_hba.conf
rm -f server.csr ca.srl

if [[ $EUID -eq 0 ]] && getent group 999 >/dev/null 2>&1; then
  chown 999:999 server.key ca.key
elif [[ $EUID -eq 0 ]]; then
  chown 999:999 server.key ca.key
else
  echo "Warning: run this script with sudo so the PostgreSQL key is owned by the container user." >&2
fi

echo "Generated PostgreSQL TLS files in $(pwd)"
echo "Keep ca.key private and store server.key outside source control."
