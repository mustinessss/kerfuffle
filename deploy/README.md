# Local Windows package

Для публичного Linux VPS используйте отдельную полную инструкцию:
[INSTALL-LINUX.md](./INSTALL-LINUX.md). Production ingress разделяет
публичные формы регистрации/начисления и закрытую административную зону
LAN/VPN; подробные настройки DNS, firewall, TLS и образов поддерживаются
только в этой инструкции.

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
applies pending Alembic migrations automatically. `down` preserves PostgreSQL
data; do not use `down --volumes` unless you intentionally want to erase it.
PostgreSQL initialization only creates the application role on a new data
volume; changing its password in `.env` does not change an existing database
role.

Useful commands from the repository root:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
docker compose --env-file deploy/.env -f deploy/compose.yaml logs -f
docker compose --env-file deploy/.env -f deploy/compose.yaml down
```

## First system administrator

After startup has completed and migrations have succeeded, run:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm backend python -m app.cli create-admin
```

Enter the administrator email and a password twice when prompted. The password
must be at least 12 characters with lowercase, uppercase, and a digit. Then
open `http://localhost:5173/login`.

## Access codes and administrator password recovery

The system administrator issues station-holder and registrar access codes in
the workspace. Staff use the codes at `/score` and `/register`; they do not
need personal accounts. For administrator password recovery, configure
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, and
`SMTP_USE_TLS` in `deploy/.env`, then recreate the backend:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --force-recreate backend
```

The administrator password-recovery link is single-use and expires after 30
minutes. This Compose package uses HTTP and is for local use only; do not expose
it on a public IP. Production deployments must configure SMTP and an
administratively reachable HTTPS `APP_PUBLIC_URL`.

## Data and production

PostgreSQL data is stored in a Docker volume. Back it up before moving the
installation or rebuilding the machine.

For production, follow [INSTALL-LINUX.md](./INSTALL-LINUX.md). The local package
does not configure LAN/VPN administration, public/private ingress separation,
HTTPS, PostgreSQL TLS, managed secrets, backups, monitoring, email delivery, or
edge rate limits.
