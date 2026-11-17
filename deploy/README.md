# Local Windows package

This Docker Compose setup is for a local demo or acceptance test on one
computer. It runs the frontend, API, and PostgreSQL over HTTP; **do not expose
it to the internet or use it as a production deployment**.

## Requirements and startup

1. Install and start Docker Desktop with the Linux container engine.
2. From the repository root, create a transfer archive:

   ```powershell
   .\deploy\package.ps1
   ```

   This creates `mustiness-kerfuffle-package.zip` and excludes local `.env`
   files, virtual environments, Node dependencies, and build caches. Verify
   that the archive contains no organization-specific data before sharing it.
3. Extract the archive on the target machine and run:

   ```powershell
   .\deploy\start.ps1
   ```

   On first run, the script creates `deploy/.env` with random database and
   access-code secrets, builds the images, applies database migrations, and
   starts the services. The web app is at `http://localhost:5173`.
4. Keep `deploy/.env` private. It contains local database secrets and is
   ignored by Git; never include it in a distributable archive.

For an existing installation, back up PostgreSQL before updating. Startup
applies pending Alembic migrations automatically. The local-auth migration
preserves event/participant data and legacy identity IDs; it adds account,
session, invitation, password-reset, and rate-limit tables. Resolve any
case-insensitive duplicate user emails before upgrading.

Useful commands from the repository root:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
docker compose --env-file deploy/.env -f deploy/compose.yaml logs -f
docker compose --env-file deploy/.env -f deploy/compose.yaml down
```

`down` preserves PostgreSQL data. Do not use `down --volumes` unless you
intentionally want to erase it. PostgreSQL initialization only creates the
application role on a new data volume; changing its password in `.env` does
not change an existing database role.

## First system administrator

After startup has completed and migrations have succeeded, run:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm backend python -m app.cli create-admin
```

Enter the administrator email and a password twice when prompted. The password
must be at least 12 characters with lowercase, uppercase, and a digit. Then
open `http://localhost:5173/login`.

## Organizer accounts and recovery

The system administrator creates organizer invitations at
`http://localhost:5173/admin/users`. For real email delivery, configure
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, and
`SMTP_USE_TLS` in `deploy/.env`, then recreate the backend:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --force-recreate backend
```

Without SMTP, development mode shows invitation links only to a signed-in
system administrator. The user-management page can also create a single-use
password-reset link (30-minute expiry) for testing. This Compose package uses
HTTP and is for local use only; do not expose it on a public IP. For a separate
HTTPS production deployment, `MANUAL_AUTH_LINKS_ENABLED=true` allows system
administrators to copy invitation and password-reset links for handoff through
a trusted channel. Configure an externally reachable HTTPS `APP_PUBLIC_URL`;
the links expire after 24 hours (invitations) or 30 minutes (password resets).

## Data and production

PostgreSQL data is stored in a Docker volume. Back it up before moving the
installation or rebuilding the machine.

For production, use the separate checklist in the root `README.md` and
`backend/README.md`: this local package does not configure HTTPS, PostgreSQL
TLS, managed secrets, backups, monitoring, email delivery, or edge
rate-limits.

# Linux VPS production deployment

This section is separate from the local Windows package.

## VPS requirements

- A Linux VPS with a public IPv4 address (at least 2 GB RAM is recommended).
- A DNS A record for the application domain pointing to the VPS.
- Docker Engine and the Docker Compose plugin.
- Public TCP ports 80 and 443. Do not publish PostgreSQL or backend ports.

On Ubuntu, Docker may be installed with the official convenience installer:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
# Log out and back in, then verify:
docker compose version
```

Wait for DNS propagation and verify the record:

```bash
getent hosts kerfuffle.example.com
```

## Firewall

Example UFW policy:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
sudo ufw status
```

Do not open PostgreSQL or backend ports. Run these commands yourself.

## Environment and secrets

From the repository root:

```bash
cp deploy/.env.production.example deploy/.env.production
nano deploy/.env.production
chmod 0600 deploy/.env.production
```

Set:

- `APP_DOMAIN` to a domain such as `kerfuffle.example.com`.
- `APP_PUBLIC_URL` to `https://` plus that domain.
- `APP_ALLOWED_ORIGINS` to the same HTTPS origin.
- separate random values for `POSTGRES_PASSWORD` and `APP_DB_PASSWORD`.
- `ACCESS_CODE_HASH_SECRET` to at least 32 random characters.

Generate separate 32-byte hexadecimal values:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -base64 48
```

Do not reuse local secrets or the example values. Production must use SMTP for
all four SMTP fields, or explicitly set `MANUAL_AUTH_LINKS_ENABLED=true` and
have administrators hand out recovery links through a trusted channel.

Generate and secure the PostgreSQL internal TLS files:

```bash
sudo deploy/postgres-tls/generate-postgres-tls.sh
```

The script creates a private CA key, server key and server certificate.
`ca.key` must not be uploaded or committed; remove or store it separately after
generation. The Compose service mounts the server certificate and key read-only
and trusts the public CA certificate. PostgreSQL accepts TLS only.

## First startup

Validate Compose and the environment before starting:

```bash
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml config
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml up --build -d
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml ps
```

PostgreSQL health starts first, Alembic applies migrations once, and the backend
starts only after migration success. Inspect it with:

```bash
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml logs migrate backend
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml exec backend \
  python -m alembic current
```

The expected migration head is `0008_route_sheets`. Do not proceed after a
migration error or downgrade migration. Make a backup before updating an existing
database.

## HTTPS and first administrator

Caddy obtains and renews Let's Encrypt certificates automatically:

```bash
curl -I "https://$(sed -n 's/^APP_DOMAIN=//p' deploy/.env.production)"
curl -fsS "https://$(sed -n 's/^APP_DOMAIN=//p' deploy/.env.production)/api/v1/health"
```

Create the first administrator:

```bash
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml run --rm backend \
  python -m app.cli create-admin
```

Open `https://YOUR-DOMAIN/login` and use the shown password requirements.

## SMTP

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, and
`SMTP_USE_TLS` in `deploy/.env.production`, then recreate the backend:

```bash
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml up -d --force-recreate backend
```

Invitation and password-reset links use `APP_PUBLIC_URL`. SMTP credentials and
delivery errors must not be placed in source control or copied into tickets.

## Backup

Create a compressed, verified backup:

```bash
sudo deploy/backup-postgres.sh
```

The file is written to `deploy/backups` with a UTC timestamp and is not served
by the application. Copy backups to encrypted off-VPS storage.

Test restoration to a separate temporary database:

```bash
sudo deploy/test-restore.sh \
  deploy/backups/kerfuffle-YYYYMMDDTHHMMSSZ.sql.gz
```

The test script never restores over `kerfuffle`. A production restore must be
performed manually after stopping writes and retaining a fresh backup.

Example cron, run as the deployment user at 02:00 and 14:00:

```cron
0 2,14 * * * cd /opt/kerfuffle && /opt/kerfuffle/deploy/backup-postgres.sh >> /var/log/kerfuffle-backup.log 2>&1
```

## Update

```bash
sudo deploy/backup-postgres.sh
git pull --ff-only
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml build
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml up -d
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml ps
```

Never run Alembic downgrade. Check migration logs and public health before
reopening registration.

## Stop, restart, and diagnostics

Stop while preserving database data:

```bash
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml down
```

Restart:

```bash
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml up -d
```

Never use `down -v` or delete the `postgres-data` volume for routine operation.

Diagnostics:

```bash
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml ps
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml logs --tail=200 caddy backend db migrate
docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml exec db pg_isready -U postgres -d kerfuffle
curl -fsS "https://$(sed -n 's/^APP_DOMAIN=//p' deploy/.env.production)/api/v1/health"
```

Configure an external HTTPS monitor for `/api/v1/health`. Docker JSON logs are
limited to 10 MB per file and five files per container. Do not disclose `.env`
contents, SMTP passwords, access codes, or database dumps in diagnostics.
