# Kerfuffle Frontend

React, TypeScript and Vite frontend for Kerfuffle.

## Development

Start the backend from `../backend` first:

```powershell
python -m uvicorn app.main:app --reload
```

Then from this directory:

```powershell
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to `http://127.0.0.1:8000`.
Open a public results page with an event ID, for example
`http://localhost:5173/?eventId=1`. The board refreshes every five seconds.

Set `VITE_API_BASE_URL` to the backend API base path when deploying behind a
reverse proxy. The default `/api/v1` works with the included Vite proxy.

## Checks

```powershell
npm run build
npm run lint
```
