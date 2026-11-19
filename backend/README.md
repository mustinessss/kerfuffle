# Kerfuffle Backend

## Requirements

- Windows 10/11 and PowerShell
- Python 3.12 or newer
- PostgreSQL

## Setup (PowerShell)

From the `backend` directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Create the `kerfuffle` database as a PostgreSQL administrator. Apply versioned
migrations as the database owner; the application role does not have DDL
permissions:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:<ADMIN_PASSWORD>@127.0.0.1:5432/kerfuffle"
python -m alembic upgrade head
Remove-Item Env:DATABASE_URL
```

As an administrator connected to `kerfuffle`, create the restricted application
role using `../database/app_role.sql` and set its password with `\password
kerfuffle_app` in `psql`. Put that role's connection string in `.env` as
`DATABASE_URL`. The role can read and write application data and use identity
sequences, but cannot create or alter database objects.

For an existing database, take and verify a backup before applying pending
migrations. `0006_local_auth` preserves old external identity subjects as
`legacy_identity_subject`, adds local password/session/invitation/reset data,
and creates a case-insensitive unique index for non-null email addresses. If
emails differ only by case, the migration stops; resolve those duplicates
deliberately before retrying. Do not stamp an existing schema without comparing
it to the migrations.

## First administrator and staff accounts

After migrations are applied and `.env` points to the application database,
create the first superuser interactively:

```powershell
python -m app.cli create-admin
```

The CLI prompts for the email and password twice. Passwords must be at least
12 characters and include lowercase, uppercase, and a digit. Passwords are
stored as Argon2id hashes. The command refuses to create another initial
superuser if one already exists.

Sign in at `/login`. A system administrator can invite station holders from
`/admin/users`; invited accounts receive access only after a station is
explicitly assigned. Password recovery links expire after 30 minutes and are
single-use.
Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, and
`SMTP_USE_TLS` to deliver invitations and recovery messages. Without SMTP,
development mode returns invitation links only to an authenticated superuser;
the same page can generate reset links for testing. Production requires SMTP
unless `MANUAL_AUTH_LINKS_ENABLED=true`; with that explicit setting, only a
system administrator can view and copy the one-time invitation or reset link
for delivery through a trusted channel. SMTP takes precedence when configured,
and the link is not shown in the admin UI.

Legacy OIDC subject values are retained for migration/history only and are not
accepted for login. Existing users should be matched and activated by their
email when invited or when the initial administrator is created. Event and
participant data remain in the existing PostgreSQL database.

## Production minimum

The application is not production-ready until all of these are in place:

1. Deploy behind HTTPS on a real domain. Terminate TLS at a maintained reverse
   proxy/load balancer, expose only that proxy publicly, and serve frontend and
   `/api` from the same origin. Configure `APP_PUBLIC_URL` and
   `APP_ALLOWED_ORIGINS` with the HTTPS origin.
2. Set `ENVIRONMENT=production`. Startup validates HTTPS origins, SMTP (or
   explicit manual-link mode), a 32+ character code-hash secret, a dedicated DB
   role, and PostgreSQL TLS. The one-shot Alembic migration service sets
   `DATABASE_MIGRATION_MODE=true` to use the database owner; this exception is
   not set on the long-running backend. Manual links require an externally reachable
   `APP_PUBLIC_URL` over HTTPS; never use the local HTTP Compose setup publicly.
   `/docs`, `/redoc`, and `/openapi.json` are disabled in production.
3. Keep secrets in the hosting provider's secret manager. Enforce strong
   passwords, protect administrator accounts with MFA at the hosting/identity
   layer where available, and define account recovery and incident procedures.
4. Put PostgreSQL on a private network, require TLS, use the restricted runtime
   role, and run Alembic as a separate migration owner/job. Automate encrypted
   backups and prove that a restore works before launch.
5. Add edge-level rate limits for login, recovery, and public access-code
   verification. The built-in counters are database-backed and keyed on the
   connecting IP; configure trusted proxy handling at the edge and test the
   effective client IP before exposing it publicly.
6. Configure uptime/error monitoring, log retention and alerting. Do not log
   session/reset/invitation tokens, raw access codes, passwords, or personal
   participant data. API responses are marked `Cache-Control: no-store`;
   verify that the proxy/CDN preserves this.
7. Complete deployment-specific browser/API acceptance tests, including
   duplicate scoring, revocation of active staff sessions, account
   disable/recovery, and restore from backup. Confirm administrator access,
   station-scoped access, participant privacy/retention, and incident-response
   ownership.

Set production values through the hosting provider's environment/secrets
management; never copy local `.env` files into an image or repository. A
successful local build/test is not a substitute for staging on the target
hosting platform.

## Run and API

```powershell
python -m uvicorn app.main:app --reload --port 8001
```

Open the health check at `http://127.0.0.1:8001/api/v1/health`. Development API
docs are at `http://127.0.0.1:8001/docs`.

Important endpoints:

- Current account and session: `/api/v1/auth/me`, `/api/v1/auth/login`,
  `/api/v1/auth/logout`, `/api/v1/auth/change-password`
- Request/complete password reset: `/api/v1/public/password-reset/request`,
  `/api/v1/public/password-reset/complete`
- Superuser user/invitation management: `/api/v1/system-admin/users`,
  `/api/v1/system-admin/invitations`
- Events: `/api/v1/events`
- Stations: `/api/v1/events/{event_id}/stations`
- Route sheets (system administrator): `/api/v1/events/{event_id}/route-sheets`,
  `/api/v1/route-sheets/{route_sheet_id}`
- People search: `/api/v1/people?event_id={event_id}&query={name}`
- Participants: `/api/v1/events/{event_id}/participants`
- Participant lookup: `POST /api/v1/stations/{station_id}/participants/lookup`
- Submit score: `POST /api/v1/stations/{station_id}/scores`
- Correct/annul score: `/api/v1/scores/{score_id}`
- Public events and leaderboards:
  `/api/v1/public/events`,
  `/api/v1/public/events/{event_id}/leaderboard`
- Create/list staff codes: `/api/v1/events/{event_id}/access-codes`
- Verify staff code: `POST /api/v1/public/access/verify`
- Station-holder lookup and scoring: `/api/v1/public/access/participant-lookup`,
  `/api/v1/public/access/scores`

System administrators set each participant's six-digit registration number.
Numbers are unique within an event, enforced by the database as well as API
validation. Participant lookup uses only that number; QR lookup and QR
generation are not part of the active application.
Migration `0007_nullable_legacy_qr_token` preserves existing database values
but permits new registrations without them. Migration `0008_route_sheets`
adds named sets of stations and optional per-sheet capacity. An administrator
selects a sheet when registering if the event has any; registration transactions lock
the event row before checking route capacity, so concurrent registrations
cannot overbook a sheet. Route sheets can be edited after assignment, and
editing never changes participants' group assignment. Station holders can score
any registered participant in the event, including outside that participant's
route sheet; all valid scores count toward both leaderboard modes. A unique
database constraint prevents repeat scores for the same participant/station,
including after an annulment.
Migration `0009_remove_organizer_role` archives legacy event-role assignments,
organizer flags, and registrar access codes before removing those active roles.
It preserves participant/event data and removes the database rule that limited
scores to assigned route stations. Back up existing databases before applying
the migration; it is not run automatically outside the documented deployment
process.
The legacy QR column can be removed only in a later, separately planned
migration after the compatibility window.
Only system administrators can search, register, and list participants or
manage events, stations, route sheets, access codes, and score history. Station
holders only see their assigned stations and can lookup/score participants at
those stations. Scores remain limited to the station's configured scale.
Public leaderboards support event-wide and route-sheet modes, include
zero-score participants and tied places, and display only participant numbers
and score progress. Score corrections and annulments require a reason and
append an immutable audit record.

## Frontend

The React/Vite app lives in `../frontend`. Install Node.js LTS, then run:

```powershell
Set-Location ..\frontend
npm install
npm run dev
```

The Vite server proxies `/api` to `http://127.0.0.1:8001`.

## Tests

```powershell
python -m pytest
```

The route-capacity concurrency test is skipped unless
`KERFUFFLE_TEST_POSTGRES_URL` is set to a disposable PostgreSQL test database.
It creates and drops a uniquely named schema; never point it at production or
the local application database.
