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
schema. The current development database was compared and stamped as
`0001_initial`.

For authenticated endpoints, configure `OIDC_ISSUER`, `OIDC_AUDIENCE`, and
`OIDC_JWKS_URL` from your OIDC provider. Access tokens are validated using the
configured asymmetric signing algorithm (RS256 by default). Set
`OIDC_BOOTSTRAP_ADMIN_SUBJECT` to the first administrator's exact `sub` claim
before their first login. Other accounts must already exist in `users` and be
granted event access.

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
- Correct score: `PATCH /api/v1/scores/{score_id}` (organizer only)
- Public leaderboard: `/api/v1/public/events/{event_id}/leaderboard`

The health endpoint checks its connection to PostgreSQL. Registration numbers
are sequential within an event, start at `0001`, and are allocated while
locking the event row; QR tokens are random UUIDs. Organizers and registrars
can search and list participants. Station operators only see their assigned
stations and receive no optional personal data. Scores are limited to the
assigned station and its configured scale. Public leaderboards include
zero-score participants, progress, and tied places without personal data.

## Frontend

The React/Vite app lives in `../frontend`. Install Node.js LTS, then in that
directory run:

```powershell
npm install
npm run dev
```

Vite proxies `/api` requests to `http://127.0.0.1:8000`. Open the public board
with an event ID, for example `http://localhost:5173/?eventId=1`.

## Tests

```powershell
python -m pytest
```
