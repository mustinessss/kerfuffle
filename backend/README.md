# Kerfuffle Backend

## Requirements
- Windows 10/11
- Python 3.12 or newer
- PostgreSQL
- PowerShell

## Setup (PowerShell)

From the `backend` directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Create the `kerfuffle` database as a PostgreSQL administrator. Apply the
versioned schema migration as the database owner; the application role does
not have DDL permissions:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:<ADMIN_PASSWORD>@127.0.0.1:5432/kerfuffle"
python -m alembic upgrade head
Remove-Item Env:DATABASE_URL
```

As an administrator connected to `kerfuffle`, create the restricted application
role using `../database/app_role.sql` and set its password with `\password
kerfuffle_app` in `psql`. Then set `DATABASE_URL` in `.env` to the application
role credentials. That role can read and write application data and use
identity sequences, but cannot create or alter database objects.

If a database already has the schema from `../database/schema.sql`, compare it
with the ORM/migration before stamping the baseline; never stamp an unverified
schema. The development database was compared and stamped as `0001_initial`,
then upgraded through `0004_immutable_score_audit`. For other existing
databases, apply all pending migrations before running the updated backend.

For authenticated endpoints, configure `OIDC_ISSUER`, `OIDC_AUDIENCE`, and
`OIDC_JWKS_URL` from your OIDC provider (local Keycloak defaults are in
`.env.example`). Access tokens are validated using the configured asymmetric
signing algorithm (RS256 by default). Set
`OIDC_BOOTSTRAP_ADMIN_SUBJECT` to the first administrator's exact `sub` claim
before their first login. Other accounts must already exist in `users` and be
granted event access. A system administrator can provision organizer accounts
through Keycloak; create a confidential Keycloak client with service accounts
enabled, grant its service account only the `realm-management` `manage-users`
role, and set `KEYCLOAK_ADMIN_BASE_URL`, `KEYCLOAK_ADMIN_REALM`,
`KEYCLOAK_ADMIN_CLIENT_ID`, and `KEYCLOAK_ADMIN_CLIENT_SECRET` in the backend
`.env`. Never expose this client secret to the frontend. The backend generates
a temporary password, returns it once, and requires the organizer to change it
at first login.

The `0005_scoped_access_codes` migration adds organizer status and hashed,
event-scoped registration/station access codes. Apply it as the database owner
before deploying the updated API; the restricted `kerfuffle_app` role is not
allowed to run migrations. Organizer codes are shown only at creation, can be
re-issued by creating a replacement, and can be disabled to revoke their
existing sessions. Staff sessions expire after 12 hours; codes themselves have
no expiry or use limit.

## Run

```powershell
python -m uvicorn app.main:app --reload
```

Open:
- API: http://127.0.0.1:8000/
- Swagger: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/v1/health
- Current account: `/api/v1/me` (requires OIDC access token)
- Events: `/api/v1/events`
- Stations: `/api/v1/events/{event_id}/stations`
- People search: `/api/v1/people?event_id={event_id}&query={name}`
- Participants: `/api/v1/events/{event_id}/participants`
- Participant lookup: `POST /api/v1/stations/{station_id}/participants/lookup`
- Submit score: `POST /api/v1/stations/{station_id}/scores`
- Correct score with required reason: `PATCH /api/v1/scores/{score_id}` (organizer only)
- Annul score with required reason: `POST /api/v1/scores/{score_id}/annul` (organizer only)
- Event score history: `GET /api/v1/events/{event_id}/scores` (organizer only)
- Public leaderboard: `/api/v1/public/events/{event_id}/leaderboard`
- Provision organizer (system administrator): `POST /api/v1/system-admin/organizers`
- Create/list event access codes (organizer): `/api/v1/events/{event_id}/access-codes`
- Disable an access code (organizer): `DELETE /api/v1/access-codes/{code_id}`
- Verify a staff code: `POST /api/v1/public/access/verify`
- Register or score with its scoped staff session: `/api/v1/public/access/register`,
  `/api/v1/public/access/participant-lookup`, `/api/v1/public/access/scores`

The health endpoint checks its connection to PostgreSQL. Registration numbers
are sequential six-digit numbers within an event, start at `000001`, and are
allocated while locking the event row. The `0002_six_digit_ids` migration pads
existing numeric numbers and aborts rather than silently
truncating invalid or conflicting data. QR tokens are random UUIDs. Organizers
and registrars can search and list participants. Station operators only see
their assigned stations and receive no optional personal data. Scores are
limited to the assigned station and its configured scale. Public leaderboards
include participant first/last names, registration numbers, per-station
progress, zero-score participants, and tied places; contacts and other optional
personal data are not included. Organizer score corrections and annulments
require a reason and append an immutable audit record; annulled scores remain
reserved for that participant/station and are excluded from public totals.
Database triggers prevent audit rows from being updated or deleted.

## Frontend

The React/Vite app lives in `../frontend`. Install Node.js LTS, then in that
directory run:

```powershell
npm install
npm run dev
```

Vite proxies `/api` requests to `http://127.0.0.1:8000`. Open the public board
with an event ID, for example `http://localhost:5173/leaderboard?eventId=1`.

## Tests

```powershell
python -m pytest
```
