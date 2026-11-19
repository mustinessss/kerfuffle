# Kerfuffle Frontend

React, TypeScript and Vite frontend for Kerfuffle.

## Development

Start PostgreSQL and the backend first. In PowerShell from the repository root:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

In another PowerShell:

```powershell
Set-Location frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to `http://127.0.0.1:8001`.
The public board lets visitors select an event by name and choose either the
overall leaderboard or a route sheet. It uses the API and refreshes every five
seconds.

Set `VITE_API_BASE_URL` to the backend API base path when deploying behind a
reverse proxy. The default `/api/v1` works with the included Vite proxy.

## Authentication

System administrators sign in at `/login`. The first administrator is created
from the backend with `python -m app.cli create-admin`. Administrators can
invite station holders from `/admin/users` and assign each account only to
specific stations. Password recovery uses a single-use link valid for 30
minutes. Production deployments must configure SMTP. Without SMTP, development
invitations and administrator-generated password-reset links are shown only to
a signed-in system administrator.

Authentication uses an HttpOnly session cookie and CSRF protection. Staff
sessions created with event-scoped access codes are separate and remain
independent of user accounts.

## User flows

- System administrators manage events and participants in `/workspace`;
  `/register` is an administrator-only participant registration form. It
  requires a manually assigned, unique six-digit number and records workplace
  or study place and phone.
- Administrators create and edit route sheets with station checkboxes, select
  all or clear all, and see the selected-station count.
- Station staff enter a code already bound to their station at `/score`.
  The backend determines the event and station and enforces the configured
  score scale. They can score any participant in their event, even when their
  station is not included in that participant's route sheet.
- Administrator-created staff codes use 8–16 Latin letters/digits (I/O/0/1 are
  excluded), are case-insensitive, and are stored only as HMAC hashes.
  Disabling a code revokes its sessions; staff sessions expire after 12 hours.
- Public leaderboards include zero-point participants and ties; they display
  only participant numbers and scores, never names or contact information.
- Administrator score corrections and annulments require a reason and are
  stored in an immutable audit log.

Event lifecycle controls (pausing/closing registration and scoring) are not
implemented yet.

## Checks

```powershell
npm run build
npm run lint
```
