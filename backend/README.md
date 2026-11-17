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

## First administrator and organizer invitations

After migrations are applied and `.env` points to the application database,
create the first superuser interactively:

```powershell
python -m app.cli create-admin
```

The CLI prompts for the email and password twice. Passwords must be at least
12 characters and include lowercase, uppercase, and a digit. Passwords are
stored as Argon2id hashes. The command refuses to create another initial
superuser if one already exists.

Sign in at `/login`. A superuser can invite organizers from `/admin/users`;
organizers activate accounts with a one-time email link that expires after 24
hours. Password recovery links expire after 30 minutes and are single-use.
Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, and
`SMTP_USE_TLS` to deliver invitations and recovery messages. Without SMTP,
development mode returns invitation links only to an authenticated superuser;
the same page can generate local reset links for testing. Production requires
SMTP and will not expose local reset links.

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
2. Set `ENVIRONMENT=production`. Startup validates HTTPS origins, SMTP, a
   32+ character code-hash secret, a dedicated DB role, and PostgreSQL TLS.
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
   disable/recovery, and restore from backup. Confirm organizer access,
   participant privacy/retention, and incident-response ownership.

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
- Route sheets: `/api/v1/events/{event_id}/route-sheets`,
  `/api/v1/route-sheets/{route_sheet_id}`; registrar codes list available sheets
  at `/api/v1/public/access/route-sheets`
- People search: `/api/v1/people?event_id={event_id}&query={name}`
- Participants: `/api/v1/events/{event_id}/participants`
- Participant lookup: `POST /api/v1/stations/{station_id}/participants/lookup`
- Submit score: `POST /api/v1/stations/{station_id}/scores`
- Correct/annul score: `/api/v1/scores/{score_id}`
- Public leaderboard: `/api/v1/public/events/{event_id}/leaderboard`
- Create/list staff codes: `/api/v1/events/{event_id}/access-codes`
- Verify staff code: `POST /api/v1/public/access/verify`
- Staff registration, lookup, and scoring: `/api/v1/public/access/register`,
  `/api/v1/public/access/participant-lookup`,
  `/api/v1/public/access/scores`

Registration numbers are sequential six-digit numbers within an event and are
allocated while locking the event row. Participant lookup uses only that
number; QR lookup and QR generation are not part of the active application.
Migration `0007_nullable_legacy_qr_token` preserves existing database values
but permits new registrations without them. Migration `0008_route_sheets`
adds named sets of stations and optional per-sheet capacity. A registrar selects
a sheet when registering if the event has any; scoring is allowed only at
stations in that participant's sheet. Events without sheets retain unrestricted
registration and scoring. Registration transactions lock the event row before
checking both sequential numbers and route capacity, so concurrent registrations
cannot overbook a sheet. The sheet's station set is immutable after the first
participant is assigned. These migrations are not applied automatically outside
the documented deployment process; back up existing databases before upgrading.
The legacy QR column can be removed only in a later, separately planned
migration after the compatibility window.
Organizers and registrars can search and list participants. Station operators
only see their assigned stations and receive no optional personal data. Scores
are limited to the assigned station and its configured scale. Public
leaderboards include participant names, registration numbers, station
progress, zero-score participants, and tied places; contacts and other
optional personal data are not included. Score corrections and annulments
require a reason and append an immutable audit record.

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
