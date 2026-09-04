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
| IATF 16949:2016 | Automotive-specific quality management framework (nonconforming product control, records, operational control) | Does not define numeric scratch/dent acceptance thresholds |
| ISO 1101:2017 | Language and interpretation of geometrical tolerancing | Actual limits must come from an approved drawing |
| ISO 9001:2015 | Documented information, control, evaluation, and improvement | Does not supply product acceptance limits |
| AIAG CQI-8 | Layered process audit governance and effectiveness | Licensed detail must be supplied by the organization |
| FNS-SEVERITY-CRITERIA-INTERNAL | Internal `DRAFT` mm severity bands for scratch/dent (`SCRATCH01-05`, `DENT01-05`): scratch ≤50/50-100/>100mm (C/B/A) follows the Japan used-vehicle auction-sheet scratch-length grading convention (A1/A2/A3); dent ≤25/25-50/>50mm (C/B/A) follows the PDR (Paintless Dent Repair) industry dent-diameter reference chart | Working assumption grounded in a real, independently checkable industry convention — not an approved OEM control plan; both source conventions apply to used-vehicle grading / consumer PDR, more lenient than new-vehicle-release acceptance |

Sources and policies are stored in Postgres (`policy_sources`/`policies` tables,
`backend/app/database.py`, seeded once by `_seed_policy_catalog()`) and returned
by `GET /api/policies`. This replaced a container-local JSON file
(`agent/policies/qc_policy_catalog.json`, now deleted) that was baked into the
Docker image at build time — any policy/source a supervisor created or edited
live via the "Chính sách QC" UI was silently lost on the next deploy
(`docker compose up --build` recreates the container from a fresh image). Edits
are now durable across deploys, same as every other catalog in this project.

Each `defect_catalog` row (`backend/app/database.py`, `SCRATCH01-05`/`DENT01-05`)
carries its own `source_id` pointing back into the same `policy_sources` register —
all 10 default rows currently cite `FNS-SEVERITY-CRITERIA-INTERNAL`. `GET
/api/qc/defect-codes` enriches each row with that source's
`document_status`/`title` (looked up from `PolicyCatalog.sources`, not a second
registry), so the API surfaces the same DRAFT/APPROVED status a client already
gets for policies. Severity is no longer an orphaned number — it always
resolves to a citable, status-tracked document.

The seeded catalog has 7 policies matching the real CV taxonomy of the MVP
(`scratch`/`dent` only, `agent/services/yolo_detector.py`), each scoped to a
specific severity band via `defect_codes` (see below) instead of the whole
`defect_type`: `SCRATCH01`→`FNS-SURFACE-PASS-001` (PASS), `SCRATCH02-03`→
`FNS-SURFACE-001` (FAIL), `SCRATCH04-05`→`FNS-SURFACE-HITL-001` (HITL);
`DENT01`→`FNS-GEOMETRY-PASS-001` (PASS), `DENT02-03`→`FNS-GEOMETRY-001` (FAIL),
`DENT04-05`→`FNS-GEOMETRY-HITL-001` (HITL); repeated defects across vehicles →
`FNS-TREND-001` (`PRD.md` §7.1, reached only via `evaluate_named`, never the
generic `evaluate()` scan). Earlier demo entries for `weld_imperfection`,
`vin_mismatch`/`vin_unreadable`, `glass_shatter`/`lamp_broken`/`tire_flat`,
`paint_defect`, and `crack` were removed — none of those are in
`agent/services/yolo_detector.py`'s CLASS_MAP, so they were never reachable
through the automatic flow.

### `defect_codes`: scoping a policy below `defect_types`

A policy may optionally set `defect_codes` (a list of `defect_catalog` codes,
e.g. `["DENT02", "DENT03"]`) to govern only those specific codes instead of
every finding of its `defect_types` — `PolicyCatalog._matches_defect_code`
(`agent/services/policy.py`). Left empty/unset, a policy is unrestricted within
its `defect_types`, exactly as before this field existed. The Supervisor
"Chính sách QC" form (`frontend/src/routes/supervisor/rules.tsx`) exposes this
as a checkbox list scoped to the selected `defect_types`.

`PolicyCatalog.evaluate()` is a **first-match-wins** scan over `policies` in
their stored `sort_order` (`backend/app/database.py`'s `policies.sort_order`
column — the original JSON array order this table replaced; `list_policies()`
always `ORDER BY sort_order`). A newly created policy always sorts last
(`Database.create_policy` assigns `MAX(sort_order) + 1`). This means a new,
*unrestricted* policy for a `defect_type` that's already fully covered by
earlier, narrower `defect_codes`-scoped policies is silently unreachable — it
will never actually decide any inspection. The Rules form computes this
client-side (`computeShadowWarnings` in `rules.tsx`, using the already-loaded
`usePolicyCatalog()` data — no extra request) and shows a non-blocking warning
naming exactly which codes would be shadowed and by which existing policy, so
a supervisor authoring a new policy sees the conflict before saving it.

## Policy không được quyết định trực tiếp từ nhãn CV thô

`PolicyCatalog.evaluate()` (`agent/services/policy.py`) không match
`defect_types` theo `state["defect_type"]` (nhãn thô YOLO trả về) nữa, mà
theo `state["catalog_defect_type"]` — trường này chỉ được set khi
`defect_catalog` đã xác nhận một `defect_code` hợp lệ cho phát hiện đó (qua
`classify_defect_code`, hoặc qua override thủ công của operator đã được xác
minh với `get_defect_code`). Nếu chưa có mã lỗi nào được xác nhận,
`evaluate()` trả thẳng về policy dự phòng "Fail-safe manual visual
reinspection" (`FNS-MANUAL-001`) thay vì tự suy diễn hành động từ nhãn CV
chưa qua kiểm chứng. Lý do an toàn: một nhãn CV thô (vd. "scratch") không tự
nó đủ căn cứ để chọn `action_code`/`final_status` — phải đi qua bước phân
loại có kiểm soát của `defect_catalog` trước.

## Tổng hợp nhiều lỗi phát hiện thành 1 quyết định PASS/FAIL

Một inspection có thể có nhiều lỗi (nhiều detection trên cùng 1 camera, hoặc
trải nhiều camera). `QCNodes.detect_defect` phân loại **từng detection một**
độc lập qua `defect_catalog`/rule engine (không chỉ lỗi nặng nhất mỗi camera,
không LLM — `agent/services/defect_rule_engine.py`), rồi `QCNodes.assess_result`
gọi `PolicyCatalog.evaluate()` độc lập cho từng lỗi đã phân loại đó. Quyết định
PASS/FAIL cấp xe là **worst-wins trên tập finding "confident"** (confidence
YOLO ≥ `CONFIRMED_THRESHOLD`, mặc định `0.85`, `ENVIRONMENT.md`): bất kỳ finding
confident nào được đánh giá `FAIL` thì cả xe `FAIL` ngay lập tức, **không cần
chờ** các finding khác (kể cả finding chưa đủ tin cậy hoặc chưa khớp danh mục)
được giải quyết trước — một lỗi FAIL đã chắc chắn thì xe chắc chắn phải giữ
lại, bất kể phần còn lại của ảnh còn gì mơ hồ. Xe chỉ `PASS` khi **mọi** finding
confident đều `PASS` **và** không còn finding mơ hồ nào; nếu không có FAIL
confident nào nhưng vẫn còn finding mơ hồ thì route sang HITL thay vì tự PASS.
Rule này hiện chưa cấu hình được qua `qc_policy_catalog.json` (mọi policy hiện
tại gán `final_status` cố định theo `defect_type`, không phân biệt severity) —
nếu sau này policy được tinh chỉnh để PASS một số mức độ nhẹ, cơ chế worst-wins
ở trên vẫn áp dụng đúng vì nó đánh giá trên từng lỗi thật, không gộp/bỏ sót lỗi
nào.

## Policy `checklist_status`: DRAFT vs APPROVED

Each policy in `qc_policy_catalog.json` carries its own `checklist_status`
(`DRAFT` or `APPROVED`), independent of the catalog-level `status`. This is
what a supervisor picks under "Trạng thái phê duyệt" when creating or editing
a policy in the Rules screen (`frontend/src/routes/supervisor/rules.tsx`).

`PolicyCatalog.evaluate()` (`agent/services/policy.py`) only matches a policy
for automatic routing when `checklist_status == "APPROVED"`
(`is_approved()`). A `DRAFT` policy — freshly saved, or an AI-extracted draft
the supervisor has not reviewed yet — is skipped and the inspection falls
through to the fail-safe manual-reinspection policy (`FNS-MANUAL-001`,
`final_status=FAIL`, `human_required=true`) instead of silently deciding a
real vehicle. Only flipping `checklist_status` to `APPROVED` puts a policy
into production routing. `evaluate_named()` itself is not gated this way — it
is used for the internal `FNS-TREND-001` alert lookup, and for a supervisor
applying one specific policy to resolve an escalation
(`QCNodes.supervisor_review`/`generate_recommendation` in
`agent/graph/nodes.py`); the latter caller re-checks `is_approved()` itself
before calling it, and only ever offers approved policies as a choice in the
first place (`PolicyCatalog.list_approved_policies()`), so a DRAFT policy can
still never end up deciding a real vehicle.

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

If the key is missing, or a Groq response is invalid, selects values outside
the controlled catalog/policy context, or cites an unknown source, the response
is rejected. Since 2026-08-31 this **no longer routes the inspection to HITL**
by itself: the PASS/FAIL/HITL route and `final_status` are already decided by
`assess_result`'s deterministic policy evaluation before Groq is ever called
(`agent/graph/nodes.py`), so a Groq failure only degrades the narrative —
`DeterministicReasoningService` substitutes a rule-based explanation and
`agent_reasoning_status` is marked `LLM_UNAVAILABLE_FALLBACK_DETERMINISTIC` —
without changing the decision itself (`PRD.md` FR-15, `ISSUE_REMEDIATION_PLAN.md`
mục 1). This keeps the LLM's role strictly to explanation (FR-03d): a narrative
outage must never silently convert every inspection into an unresolvable HITL
backlog. See `ENVIRONMENT.md` for the corresponding variables.
