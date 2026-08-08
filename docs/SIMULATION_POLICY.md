# Simulation Policy — Local Train Images

## Purpose

The CV Simulation Workbench demonstrates the boundary between a visual detector, deterministic QC orchestration, and human review. It is a baseline-demo facility only.

## Image annotation status

The repository contains six files in `data/train`. No accompanying YOLO label file, measurement report, material record, or approved plant work instruction is present. For that reason, each image is exposed with a **demo annotation**:

- defect type and bounding box are selected for visual demonstration;
- confidence is a mock detector score;
- panel/material/GD&T/measurement/severity values come from the existing mock rule engine;
- the image itself is not treated as a ground-truth label or a production inspection result.

The API marks every image case with:

```text
annotation_source = demo_annotation_from_local_train_image
```

## Simulation workflow

```text
select local image
  -> POST /api/simulations/{case_id}/run
  -> create SQLite inspection and mock YOLO-shaped defect payload
  -> detect -> validate -> classify -> policy_evaluate -> route -> HITL
  -> persist every completed/stopped step and show it in the workstation
```

Every stage is a checkpoint. A validation error or an injected demo failure produces
`STOPPED_RETRY_REQUIRED`, records an `error_code`, marks the step as retryable, and
does not execute any downstream stage. The workstation can retry the same image as a
clean simulation.

## Decision boundary

The current decision engine is a transparent demo policy:

| Trigger | Demo action |
|---|---|
| No detected defect | `RELEASE_TO_NEXT_QUALITY_GATE` |
| Sufficient confidence, minor in-tolerance surface defect | `SURFACE_POLISH_AND_REINSPECT` |
| Over tolerance, severe rank, or hot-stamped material | `ISOLATE_FOR_BODY_REPAIR_ASSESSMENT`; HOLD and block test drive |
| Paint/Class-A surface condition | `ISOLATE_FOR_PAINT_REPAIR_ASSESSMENT`; HOLD and block test drive |
| Confidence below 0.80 | `MANUAL_VISUAL_REINSPECTION`; named QC review required |
| Missing classification | `RETRY_CLASSIFICATION_PIPELINE`; stop downstream routing |

Each decision returns `action_code`, `policy_refs`, and ordered `method_steps` instead
of an abstract Plan A/Plan B label. References beginning with `DEMO-QC-*` are internal
baseline policies. They demonstrate fail-safe behavior and are not an OEM, plant, or
supplier standard.

## Failure simulation

Use the failure selector in **CV simulation**, or call:

```http
POST /api/simulations/{case_id}/run
Content-Type: application/json

{"fail_at_step":"classify"}
```

Supported injected checkpoints are `detect`, `validate`, `classify`, and
`policy_evaluate`. These faults exist only to demonstrate stop/retry semantics.

## Required inputs before production policy automation

To let the agent select production-valid actions, the team must obtain and version-control approved data for:

1. Panel/model/material master data.
2. GD&T zones, tolerance limits, and measurement methods.
3. PSLAWBCD severity definitions and escalation rules.
4. Approved repair work instructions, including when buffing is permitted.
5. Test-drive authorization and HOLD/release rules.
6. VIN, Stud/Nut, weld, paint, and traceability acceptance criteria.

Those sources should become controlled database tables and be approved by QC engineering. The agent must select an action only from the approved action catalog.
