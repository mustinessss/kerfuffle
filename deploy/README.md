# Local Windows package

This Docker Compose setup is for a local demo or acceptance test on one
computer. It runs the frontend, API, PostgreSQL, and Keycloak. It uses HTTP,
Keycloak `start-dev`, and a local PostgreSQL instance; **do not expose it to the
internet or use it as a production deployment**.

## Requirements and startup

1. Install and start Docker Desktop with the Linux container engine.
2. To create a clean transfer archive from the repository root, run:

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

   On first run, the script creates `deploy/.env` with random passwords and a
   random access-code hashing secret, builds the images, applies database
   migrations, and starts the services. The web app is at
   `http://localhost:5173`; Keycloak is at `http://localhost:8080`.
4. Keep `deploy/.env` private. It contains the local database and Keycloak
   administrator passwords. It is ignored by Git and must not be put in a
   distributable archive.

Useful commands from the repository root:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
docker compose --env-file deploy/.env -f deploy/compose.yaml logs -f
docker compose --env-file deploy/.env -f deploy/compose.yaml down
```

`down` preserves database and Keycloak data. Do not use `down --volumes`
unless you intentionally want to erase them. PostgreSQL initialization only
creates the application role on a new data volume; changing its password in
`.env` does not change an existing database role.

## First system administrator

1. Sign in to the Keycloak administration console using the bootstrap
   credentials in `deploy/.env`.
2. In the `kerfuffle` realm, create the initial system-administrator user.
   Set a temporary password and require a password change at first login.
3. Copy that user's Keycloak ID (`sub`) and assign the application role once:

   ```powershell
   docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm backend python -m app.cli --subject "<KEYCLOAK_USER_ID>" --display-name "System administrator"
   ```

   Confirm the subject when prompted. The command stores no password; Keycloak
   remains responsible for credentials.

## Organizer account provisioning

To let the system administrator create organizer accounts from the app:

1. In the `kerfuffle` realm, create an OpenID Connect client with ID
   `kerfuffle-user-provisioner`.
2. Enable client authentication and service accounts; disable browser and
   direct-grant flows.
3. Open its service account's role mapping, choose client roles for
   `realm-management`, and assign only `manage-users`.
4. Copy the client secret into `KEYCLOAK_ADMIN_CLIENT_SECRET` in
   `deploy/.env`, then recreate the API container:

   ```powershell
   docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --force-recreate backend
   ```

The backend generates an organizer's temporary password, displays it once,
and requires a change at first login. Deliver it separately through a secure
channel.

## Data and production

PostgreSQL and Keycloak data are stored in Docker volumes. Back up these
volumes before moving the installation or rebuilding the machine.

For production, use the separate checklist in the root `README.md` and
`backend/README.md`: this local package does not configure HTTPS, production
Keycloak, PostgreSQL TLS, managed secrets, backups, monitoring, or edge
rate-limits.
