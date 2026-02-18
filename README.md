# Lineage Explorer (Local-First)

This repository is intentionally reduced to:
- `backend/`
- `frontend/`
- `output/`

`./output` is the single source of truth for generated lineage artifacts.

## Run (Dev)

1. Backend (port `8000`)

```powershell
cd backend
python -m venv .venv
# activate .venv
python -m pip install -r requirements.txt

# backend-only Qlik credentials (required for fetch jobs)
$env:QLIK_TENANT_URL = "https://<tenant>.<region>.qlikcloud.com"
$env:QLIK_API_KEY = "<qlik_api_key>"

uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

2. Frontend (port `5173`)

```powershell
cd frontend
npm install
# optional override (default is http://127.0.0.1:8000)
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
npm run dev
```

## Run (Dev - CMD)

Use two separate CMD terminals.

1. Backend (CMD Terminal 1, port `8000`)

```cmd
cd C:\Users\MauriceOkoye\Desktop\Entwicklung\backend
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt

set QLIK_TENANT_URL=https://<tenant>.<region>.qlikcloud.com
set QLIK_API_KEY=<qlik_api_key>

python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

2. Frontend (CMD Terminal 2, port `5173`)

```cmd
cd C:\Users\MauriceOkoye\Desktop\Entwicklung\frontend
npm install
set VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

## API Expectations

Frontend uses backend HTTP endpoints only:
- `GET /api/apps`
- `GET /api/spaces`
- `GET /api/data-connections`
- `GET /api/graph/app/{appId}?depth=...`
- `GET /api/graph/node/{nodeId}?direction=...&depth=...`
- `GET /api/graph/all`
- `GET /api/app/{appId}/usage`
- `GET /api/app/{appId}/script`
- `GET /api/fetch/status`
- `GET /api/fetch/jobs`
- `GET /api/fetch/jobs/{jobId}`
- `POST /api/fetch/jobs`

No frontend token handling. No direct calls to Qlik Cloud from the frontend.

## Frontend Tabs

- `Datenfluss`: existing lineage explorer graph view.
- `Datenabzug`: starts backend fetch jobs in the correct order (spaces -> apps -> data-connections -> lineage -> app-edges -> usage), supports optional cleanup of old artifacts, and shows job status.
