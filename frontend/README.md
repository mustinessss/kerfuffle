# Kerfuffle Frontend

React, TypeScript and Vite frontend for Kerfuffle.

## Development

Start PostgreSQL, Keycloak, and the backend first. In PowerShell from the
repository root:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

In another PowerShell from the repository root:

```powershell
$env:PATH = "C:\Program Files\nodejs;" + $env:PATH
Set-Location frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to `http://127.0.0.1:8001`.
Open the public board with an event ID, for example
`http://localhost:5173/leaderboard?eventId=1`. The board uses the real API and
refreshes every five seconds.

Set `VITE_API_BASE_URL` to the backend API base path when deploying behind a
reverse proxy. The default `/api/v1` works with the included Vite proxy.

## Authentication setup

The local Keycloak realm includes the public OIDC client for organizer sign-in.
For local development only, `OIDC_BOOTSTRAP_ADMIN_SUBJECT` can bootstrap the
first administrator. For a new installation, prefer the one-time
`python -m app.cli` command documented in `backend/README.md` or
`deploy/README.md`; production must not set the bootstrap environment variable.
Configure the frontend OIDC values from `frontend/.env.example`, then restart
the backend and Vite after changing environment files.

For organizer provisioning, create a confidential client named
`kerfuffle-user-provisioner` in the `kerfuffle` realm. Enable service accounts,
disable browser and direct-grant flows, and assign the service account only the
`realm-management` role `manage-users`. Set
`KEYCLOAK_ADMIN_BASE_URL`, `KEYCLOAK_ADMIN_REALM`,
`KEYCLOAK_ADMIN_CLIENT_ID`, and `KEYCLOAK_ADMIN_CLIENT_SECRET` in
`backend/.env`. The service-account secret is backend-only and must never be
added to frontend configuration or source control. The system administrator
creates organizers from `/organizer`; the temporary password is shown once and
must be changed at first login.

## User flows

- Organizers sign in through Keycloak, create events, configure stations, and
  issue/revoke staff access codes.
- Registrars enter their event-scoped code at `/register`. After registration,
  the screen displays the participant's six-digit number.
- Station staff enter a code already bound to their station at `/score`.
  The event and station are determined by the backend; staff can look up a
  participant and submit one score using the configured step and maximum.
- The organizer chooses an 8–16 character code in the signature field. Use
  Latin letters and digits 2–9 (I/O/0/1 are excluded); input is
  case-insensitive. Avoid event/station names and other guessable values. The
  code is shown once after creation and stored only as an HMAC hash.
  Codes have no expiration or use limit; disabling a code revokes its sessions.
  Staff sessions expire after 12 hours.
- The public leaderboard shows participant names, registration numbers,
  aggregate scores, and station progress, but no contact information.
- Organizer score corrections and annulments require a reason and are stored
  in an immutable audit log.

Event lifecycle controls (pausing/closing registration and scoring) are not
implemented yet. Use the backend OpenAPI page at `/docs` as the source of truth
for API routes and permissions.

## Checks

```powershell
npm run build
npm run lint
```
