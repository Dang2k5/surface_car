# Visual QC policy governance

## Safety status

The bundled catalog is temporarily `APPROVED` with approval scope
`DEMO_BASELINE_ONLY`. This simulated internal approval supports baseline demos
and workflow validation, but it is not production release authority or a
substitute for a plant control plan, cosmetic standard, engineering drawing,
or repair instruction.

Public standards define terminology, assessment frameworks, and quality-system
controls. They do not publish the OEM-specific scratch, dent, paint, weld,
or repair acceptance limits needed to release a production vehicle. The demo
GD&T tolerance values referenced in `PRD.md` (Group 1–5) are `DEMO_BASELINE_ONLY`
and must not be presented as ISO/GD&T-mandated limits for a real vehicle.

## Controlled source register

| Source | Publicly supported scope | Explicit limitation in this project |
| --- | --- | --- |
| ISO 4628-1:2016 | Designation of coating defect quantity, size, and appearance change | Does not become an OEM cosmetic acceptance limit |
| ISO 1101:2017 | Language and interpretation of geometrical tolerancing | Actual limits must come from an approved drawing |
| ISO 17637:2016 | Visual testing of fusion-welded joints | Weld-process applicability must be confirmed |
| ISO 5817:2023 | Quality levels B/C/D for covered fusion-weld imperfections | No default level is assigned; it is not a spot-weld acceptance rule |
| ISO 3779:2009 | VIN content and structure | Market and build-record checks remain required |
| ISO 9001:2015 | Documented information, control, evaluation, and improvement | Does not supply product acceptance limits |
| AIAG CQI-8 | Layered process audit governance and effectiveness | Licensed detail must be supplied by the organization |

Source links are stored in `agent/policies/qc_policy_catalog.json` and returned
by `GET /api/policies`.

`qc_policy_catalog.json` là một controlled document register rộng hơn CV
taxonomy hiện tại của MVP — nó còn giữ entry cho `weld_imperfection`,
`vin_mismatch`/`vin_unreadable`, `paint_defect`, `lamp_broken`, `tire_flat`
(tham chiếu tới ISO 17637/5817/3779 ở trên) để phục vụ tra cứu chính sách
đầy đủ. Trong baseline MVP, node `decide` chỉ có thể route tới các entry có
`defect_types` khớp taxonomy CV thật (`scratch`, `dent` — `PRD.md` §7.1); các
entry khác trong register là tài liệu tham chiếu, chưa reachable qua luồng
tự động cho tới khi taxonomy được mở rộng (`PRD.md` §11).

## Component responsibilities and decision authority

The Visual QC Agent is the full pipeline described in `PRD.md` (§2), not a
single model. Each component has a bounded responsibility:

1. **YOLO Segmentation** supplies evidence: class, confidence, bounding box,
   segmentation mask/polygon.
2. **Geometry Processor** computes deterministic mask geometry (`area_px`,
   `centroid`, `orientation_deg`, `aspect_ratio`, ...) with OpenCV/NumPy. It
   never calls an LLM and never guesses a value it cannot compute from the
   mask.
3. **LangGraph Agent** (node graph `ingest → detect →
   extract_visual_geometry → classify → decide →
   decision_gate → (final_decide | HITL → human_review → resume →
   final_decide) → explain → complete → update_trend`) decides whether the
   evidence is confirmed, requires verification, or must stop at HITL.
   `explain` always runs **after** the final decision (post-HITL when HITL
   is triggered) — never before, since a human confirm/override can change
   the outcome. See `PRD.md` §7.4 and `AGENT_FLOW.md` for the current
   runtime node names.
4. **QC Rules** is a controlled decision tool (rule-based logic / decision
   table / JSON / database policy table) that runs **inside** the LangGraph
   Agent — it is not a standalone `Policy Engine` microservice in this MVP.
   It selects only a controlled action code and identifies missing evidence.
   QC Rules must come from controlled project policy or approved plant
   policy in production, never from free-form LLM inference.
5. The reasoning/explanation LLM may explain the immutable result. It cannot
   change the action, final status, test-drive gate, references, or
   measurements.
6. A catalog that is not `APPROVED`, or a decision with missing evidence, has
   `production_eligible=false`.
7. Production release requires an approved plant policy and accountable QC
   sign-off.

## Data provenance

Every field group returned by the pipeline must be traceable to one source.
The API/documentation is not required to attach a `source` field to every
individual field when that would over-complicate the schema, but each field
group's provenance must be documented explicitly:

```text
source = yolo                 → class, confidence, bbox, mask/polygon
source = geometry_processor   → area_px, centroid, orientation_deg, aspect_ratio
source = camera_calibration   → mm conversion, calibration_profile_id
source = depth_sensor         → depth_mm (when a depth sensor is present)
source = human_qc             → HITL confirm/reject/change/recapture decisions
source = qc_policy            → QC Rules, tolerance, recommendation_code
```

## RBAC and decision authority by role

Login/session baseline uses **Supabase Auth** as the single authentication
provider — the project does not build a parallel bespoke login system. Role
is not a native Supabase Auth attribute; it is stored in a `profiles` table
(PostgreSQL/Supabase, `profiles.user_id → auth.users.id`, column `role`).
FastAPI backend never issues its own session token; it only verifies the
Supabase-issued access token (`SUPABASE_JWT_SECRET`) and looks up
`profiles.role` to authorize each request — see `API_CONTRACT.md` §6.7 and
`ENVIRONMENT.md`.

- `QC_OPERATOR`: performs inspection, uploads image/video, views
  segmentation/geometry/visual assessment, views PASS/FAIL/explanation,
  resolves HITL cases assigned to them, views required history. Cannot
  modify QC Rules or approve overrides outside an assigned HITL case.
- `QC_SUPERVISOR`: has all `QC_OPERATOR` permissions, plus shift/lot
  dashboard, anomaly alerts, historical trend, override approval where in
  project scope, and QC Rules management within project scope. See
  `PRD.md` §4 and §7.6 (FR-16) and `UI_WORKFLOWS.md` for UI-level detail.

Any override of a final decision must be attributed to the authenticated
role that performed it (resolved from `profiles.role` at request time) and
recorded in the audit trail.

## Plant approval checklist

Before changing approval scope from `DEMO_BASELINE_ONLY` to `PRODUCTION`,
Quality Engineering must attach:

- OEM cosmetic acceptance standard by model and visual zone;
- released drawings and GD&T limits;
- approved repair restrictions;
- weld process and acceptance-level mapping;
- stud/nut BOM, presence/count, torque, and rework requirements;
- VIN market/build-record validation rules;
- work instructions with revision and effective date;
- role/authority matrix for PASS, HOLD, concession, and release;
- validation evidence showing that each encoded rule matches the controlled source;
- an authoritative material source (`vehicle_id → MES/BOM → panel/material
  mapping`) if material-aware reasoning (`PRD.md` §11) is enabled.

## Groq reasoning configuration

Create a project-specific key in the Groq Console. Never place it in frontend
code or commit it to Git.

```dotenv
QC_REASONING_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-20b
```

If the key is missing, the LLM Agent is marked unavailable and the graph routes
the inspection to HITL. If a Groq response is invalid, selects values outside
the controlled catalog/policy context, or cites an unknown source, the response
is rejected and no deterministic output is presented as Agent reasoning. This
applies to both the reasoning/explanation call and, when the same or a
separate multimodal-capable model is used for visual verification, the
image-input call — see `ENVIRONMENT.md` for the corresponding variables.
