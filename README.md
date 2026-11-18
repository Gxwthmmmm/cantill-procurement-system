# Cantill Procurement

Policy-driven purchase request workflow prototype for the Cantill.ai full-stack challenge.

## Stack
- Frontend: React, TypeScript, Vite
- Backend: FastAPI, SQLAlchemy
- Database: PostgreSQL

## Local setup (Windows / PowerShell)

### 1. PostgreSQL
Install PostgreSQL locally and ensure the PostgreSQL service is running. Create a database:

```powershell
psql -U postgres -c "CREATE DATABASE cantill_procurement;"
```

If you prefer Docker for only the database, run `docker compose up -d db` instead. Do not run both local PostgreSQL and Docker PostgreSQL on port 5432 simultaneously.

### 2. Backend

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` if your PostgreSQL username/password/port differs. Then:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m scripts.import_task_data
python -m scripts.seed_policy
uvicorn app.main:app --reload
```

API: http://localhost:8000 · Swagger: http://localhost:8000/docs

### 3. Frontend (new terminal)

```powershell
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

## Initial API endpoints
- `GET /api/health` — API/database health
- `GET /api/data/summary` — imported record counts
- `POST /api/data/import` — idempotently re-import task-kit CSV data
- `GET /api/data/{dataset}?limit=20` — inspect staged source rows
- `GET /api/policies` — list policy versions

## Notes
The source CSV rows are preserved in a JSONB staging table during Phase 1. This lets us validate and explore the supplied data without losing source columns. Later phases will add typed procurement entities, decision logic, policy amendments, approvals, and audit workflows. Policy v5.0 is seeded as structured data; this initial seed is a representation of the supplied PDF, not yet the full policy execution engine.
