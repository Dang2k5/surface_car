# Visual QC Agent backend

FastAPI, SQLite and LangGraph backend for the mock-first FNS Visual QC demo.

## Run

From the repository root, after installing [requirements.txt](../requirements.txt):

```powershell
python -m uvicorn backend.app.main:app --reload
```

Open Swagger at `http://127.0.0.1:8000/docs`. The default SQLite database is `data/visual_qc.db`; set `DATABASE_URL` in the root `.env` to use another SQLite file.

## Workflow

Every newly-created inspection and every seeded inspection automatically runs:

```text
detect -> validate -> classify -> policy evaluation -> controlled route -> HITL
```

`GET /api/inspections/{inspection_id}/workflows/latest` retrieves its result. `POST /api/inspections/{inspection_id}/run-workflow` is provided only to rerun a case during debugging.

The new checkpointed LangGraph API is:

```text
POST /inspections                       start a graph thread
GET  /inspections/{thread_id}/state     inspect checkpointed state
POST /inspections/{thread_id}/resume    resume an interrupted HITL thread
GET  /agent/graph                       return generated Mermaid
```

The `/api/langgraph/...` aliases are available when a prefixed route is preferred.
Development uses `InMemorySaver`; completed graph results are upserted into the
SQLite `agent_graph_runs` table.

The visible inspection feed is intentionally curated: `GET /api/inspections`
returns only records with `source_image_url` and a persisted Agent decision.
`POST /api/mock/seed?reset=true` now resets the old data and creates the six local
image cases from `data/train`; it no longer creates the legacy image-less fleet.

The policy engine returns concrete action codes such as
`SURFACE_POLISH_AND_REINSPECT`, `ISOLATE_FOR_BODY_REPAIR_ASSESSMENT`,
`ISOLATE_FOR_PAINT_REPAIR_ASSESSMENT`, and `MANUAL_VISUAL_REINSPECTION`.
Every result includes ordered method steps and `DEMO-QC-*` policy references. A failed
checkpoint stops downstream execution with `STOPPED_RETRY_REQUIRED`. All tolerances,
materials, severity values, policy references, and methods remain placeholders until
plant-approved controlled data replaces them.

## Common API calls in PowerShell

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/mock/seed?reset=true"
Invoke-RestMethod http://127.0.0.1:8000/api/inspections
Invoke-RestMethod http://127.0.0.1:8000/api/mock/yolo-detections
```

The YOLO mock payload provides `class_id`, `class_name`, confidence, an `xyxy` pixel bounding box, and image/model metadata.

`POST /inspections/stream` returns NDJSON node updates for the live workstation.
`GET /agent/runs` returns the same persisted LangGraph states used by History and
the QC review queue.
`DELETE /agent/runs` clears only persisted Agent traces and development HITL
checkpoints; source images and mock case definitions are preserved.
