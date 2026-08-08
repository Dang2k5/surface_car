# Visual QC Agent for FNS

Mock-first demo for an automotive final-inspection station. The current build demonstrates both the stable baseline API and the checkpointed LangGraph flow:

```text
image input -> detect -> assess -> verify loop / HITL -> recommendation -> persist
```

It includes mock defects for dents, scratches, and paint defects; deterministic,
policy-referenced repair/reinspection methods; checkpoint pause/resume behavior; a
FastAPI backend; SQLite; and a Next.js/React
dashboard. It does **not** use a production YOLO model, approved plant GD&T data,
PostgreSQL, MinIO, or a production CV model yet. LangGraph orchestration is active
with an in-memory development checkpointer and SQLite final-result persistence.

## Requirements

- Git
- Python 3.11 or newer (3.11 is recommended)
- Node.js 22.13 or newer for the frontend
- Docker Desktop only if you want to run the backend in Docker

Check installed versions:

```powershell
python --version
node --version
npm --version
```

## Run on a new machine

Clone the repository, then open PowerShell in the repository folder.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload
```

If PowerShell blocks activation, run this once for the current window and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

In a second PowerShell window, start the frontend:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Open the URL printed by the frontend server (normally `http://localhost:3000`). Swagger is available at `http://127.0.0.1:8000/docs`.

## Demo flow

1. Open **Agent inspection** and select one of eight image-backed vehicle examples.
2. Press **Start inspection**. The example carries its own mock CV profile, so no
   test-branch selector is required.
3. Watch node updates stream from LangGraph one at a time while image evidence,
   state and the operational outcome remain in the same workstation.
4. For an uncertain case, approve or reject at the real HITL checkpoint. The same
   thread resumes, completes and is recorded in History.

## Verify the installation

From the repository root, with the virtual environment active:

```powershell
python -m pytest -q
```

From `frontend`:

```powershell
npm run build
```

The expected baseline result is a passing backend test suite and a successful
frontend production build. No Gemini/OpenAI API key is required: routing,
verification and recommendations are deterministic in this MVP.

Useful backend checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/mock/seed?reset=true"
Invoke-RestMethod http://127.0.0.1:8000/api/inspections
```

`curl` is an alias for `Invoke-WebRequest` in Windows PowerShell, so use `Invoke-RestMethod` as above, or explicitly call `curl.exe`.

## Docker backend (optional)

After copying `.env`, run:

```powershell
docker compose up --build
```

The container serves the backend at `http://127.0.0.1:8000`. The frontend remains a local Node process and should be started with `npm run dev`.

## Project layout

```text
backend/       FastAPI API, SQLite persistence, mock QC routes
agent/         LangGraph state, nodes, routing and injectable service adapters
frontend/      bilingual Next.js/React dashboard
tests/         backend API tests
data/          local SQLite database (generated; not committed)
```

More API detail is in [backend/README.md](backend/README.md), and frontend-only setup is in [frontend/README.md](frontend/README.md).
The complete graph/state/HITL explanation is in [agent/README.md](agent/README.md)
and [AGENT_FLOW.md](AGENT_FLOW.md).
The local image simulation policy and its production boundary are documented in [docs/SIMULATION_POLICY.md](docs/SIMULATION_POLICY.md).

## Troubleshooting

- `spawn EINVAL` or frontend startup errors: upgrade to Node.js 22.13+ and reopen PowerShell.
- A copied or moved virtual environment may reference a Python installation that
  no longer exists. Delete only that local `.venv`/`.venv-new` folder, recreate it
  with `python -m venv .venv`, and reinstall `requirements.txt`.
- Port 8000 is busy: stop the old Uvicorn process, or add `--port 8001` and set `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001` in `frontend/.env.local`.
- To reset demo records, call `POST /api/mock/seed?reset=true`. It deletes old QC
  records and recreates only the eight image-backed cases from `data/train`.
- `GET /api/inspections` returns only image-backed inspections with a persisted
  Agent decision. Incomplete, failed, or image-less records are hidden from the UI.
