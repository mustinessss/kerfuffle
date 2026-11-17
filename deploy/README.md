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
