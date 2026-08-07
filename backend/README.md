# Visual QC Agent — Backend

FastAPI + SQLite mock backend for CP1. It is intentionally independent from the existing `src/` starter template.

Run from the repository root:

```powershell
uvicorn backend.app.main:app --reload
```

Open Swagger at `http://localhost:8000/docs`.

Useful calls:

```powershell
curl -X POST "http://localhost:8000/api/mock/seed?reset=true"
curl "http://localhost:8000/api/inspections"
curl "http://localhost:8000/api/mock/yolo-detections"
curl -X POST "http://localhost:8000/api/inspections/{inspection_id}/classify"
curl "http://localhost:8000/api/inspections/{inspection_id}/classifications"
curl -X POST "http://localhost:8000/api/inspections/{inspection_id}/decide"
curl "http://localhost:8000/api/inspections/{inspection_id}/decisions"
curl -X POST "http://localhost:8000/api/inspections/{inspection_id}/hitl/reviews"
curl "http://localhost:8000/api/inspections/{inspection_id}/hitl/reviews"
curl -X POST "http://localhost:8000/api/inspections/{inspection_id}/run-workflow"
curl "http://localhost:8000/api/workflows/{workflow_id}"
```

`/api/mock/yolo-detections` returns the serialized YOLO contract: `class_id`, `class_name`, `confidence`, and pixel `bbox` in `xyxy` form, plus image and model metadata. The SQLite file is created at `data/visual_qc.db` and contains mock inspection and defect records only.

`/classify` applies explicitly mock domain rules and returns panel, material, GD&T group, mock tolerance/measurement, severity rank, and `is_mock=true`. These technical values are placeholders and must be replaced by approved plant data before production use.

`/decide` applies fail-safe mock rules: no defects returns `PASS`, a minor in-tolerance defect returns `PLAN_A`, an over-tolerance/high-severity/material-risk defect returns `PLAN_B`, and low confidence returns `HITL_REQUIRED`.

`/hitl/reviews` records QC confirmation, override, or rejection of the latest decision. Overrides and rejections require a reason.

`/run-workflow` is the mock agent demo. It orchestrates persisted mock YOLO detections through classify and decide, then returns a four-step trace (`detect`, `classify`, `decide`, `hitl`). A `HITL_REQUIRED` decision ends in `WAITING_FOR_HITL`; all other mock decisions complete.

Every newly created inspection and mock seed now starts this workflow automatically. Use `GET /api/inspections/{inspection_id}/workflows/latest` to retrieve its current result. `POST /run-workflow` remains available only for rerunning a mock case during debugging.

## Optional LLM explanation agent

The LLM can explain a completed workflow, but cannot make or override a technical QC decision.

```text
POST /api/inspections/{inspection_id}/agent/explain
```

Configure a new, private key in `.env` (never commit it):

```dotenv
OPENAI_API_KEY=replace_with_a_new_key
OPENAI_BASE_URL=https://api.key4u.vn/v1
OPENAI_MODEL=gpt-4o-mini
# Optional: generate a Vietnamese explanation after every automatic workflow.
QC_LLM_AUTO_EXPLAIN=false
```

For OpenAI-compatible providers, set `OPENAI_BASE_URL` to the API root ending in `/v1`, not the `/chat/completions` endpoint. Set `QC_LLM_AUTO_EXPLAIN=true` only when automatic LLM explanations are desired; the deterministic workflow will still complete if the provider is unavailable. Example body:

```json
{
  "language": "vi",
  "question": "Tóm tắt quyết định và hành động cần thực hiện cho QC."
}
```
