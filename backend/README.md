# Kerfuffle Backend

## Requirements
- Windows 10/11
- Python 3.12 (recommended)
- Local PostgreSQL
- PowerShell

## Setup (PowerShell)

From the `backend` directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `DATABASE_URL` to your PostgreSQL connection.
The database must already exist and the SQL schema in `../database/schema.sql`
must already have been applied to it.

Example URL:

```text
postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/kerfuffle
```

## Run

```powershell
uvicorn app.main:app --reload
```

Open:
- API: http://127.0.0.1:8000/
- Swagger: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/v1/health

The health endpoint runs `SELECT 1` against PostgreSQL.

## Tests

```powershell
pytest
```
