from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


class TraceEvent(TypedDict):
    node: str
    status: str
    detail: str


class QCState(TypedDict, total=False):
    """Serializable state shared by every Visual QC LangGraph node."""

    inspection_id: str
    thread_id: str
    vehicle_id: str
    vehicle_model: str
    lot_id: str | None
    shift_id: str | None
    production_date: str | None
    station_id: str
    image_url: str
    image_paths: list[str]
    camera_id: str
    camera_evidence: list[dict[str, Any]]
    camera_results: list[dict[str, Any]]
    # Set only by the video-upload endpoint (backend/app/langgraph_api.py), which already ran
    # detection across every extracted frame per camera and merged same-defect observations
    # via agent.services.video_processor.DefectDeduplicator before invoking the graph. Shaped
    # identically to DetectorService.detect()'s return value; QCNodes.detect_defect uses it
    # verbatim instead of re-running detection on a single frame, so multi-frame tracking
    # survives into the same downstream policy/assessment logic unchanged.
    precomputed_detection: dict[str, Any] | None
    finding_groups: list[dict[str, Any]]
    zone_name: str
    defect_detected: bool
    defect_type: str
    confidence: float
    bbox: dict[str, float] | None
    segmentation_result: dict[str, Any] | None
    visual_measurements: dict[str, float | str]
    detections: list[dict[str, Any]]
    primary_detection_id: str | None
    # One entry per DETECTION (not per camera) — every finding on every camera is
    # classified independently against defect_catalog/LLM (see QCNodes.detect_defect).
    # Lets assess_result decide PASS/FAIL/HITL from EVERY defect, not just the single
    # worst finding per camera.
    camera_classifications: list[dict[str, Any]]
    unresolved_camera_ids: list[str]
    camera_policy_decisions: list[dict[str, Any]]
    # Every vehicle body side (front/rear/left/right/top) that has a defect in THIS
    # inspection — one inspection combines all 5 fixed cameras, so more than one side can
    # legitimately be affected at once. `zone_name` alone only ever names ONE (the worst).
    affected_zones: list[str]
    enriched_defects: list[dict[str, Any]]
    overlay_image_url: str | None
    crop_image_url: str | None
    mask_image_url: str | None
    raw_class_name: str | None
    image_width: int
    image_height: int
    image_sha256: str | None
    model_name: str
    model_version: str
    model_task: str
    inference_ms: float
    inference_status: str
    severity: str
    measurements: dict[str, float | str | bool]
    suggested_defect_codes: list[dict[str, Any]]
    defect_code_classification: dict[str, Any]
    classified_defect_code: str | None
    defect_family: str | None
    # Set only when defect_catalog confirmed a real defect_code — PolicyCatalog.evaluate()
    # matches on this, never on the raw CV `defect_type` label directly.
    catalog_defect_type: str | None
    severity_source_id: str | None
    similar_defect_warning: bool
    evidence_tags: list[str]
    decision: str
    reason: str
    assessment_route: Literal["PASS", "CONFIRMED", "HITL"]
    human_required: bool
    human_decision: dict[str, Any] | None
    qc_decision_record: dict[str, Any] | None
    recommendation_code: str
    recommendation: str
    policy_decision: dict[str, Any]
    ai_analysis: dict[str, Any]
    agent_reasoning_status: str
    agent_analysis: dict[str, Any]
    final_status: str
    allow_test_drive: bool
    anomaly_alert: dict[str, Any] | None
    hitl_status: str
    error: str | None
    retry_count: int
    max_retries: int
    auto_pass_enabled: bool
    confirmed_threshold: float
    # Set by the upload endpoints (backend/app/langgraph_api.py) from a live
    # HitlRateAlertService.analyze() call, never persisted as sticky state — a CRITICAL HITL
    # escalation rate at this station forces EVERY new inspection through human_review
    # regardless of what assess_result would otherwise decide (agent/graph/nodes.py).
    force_human_review: bool
    # True only when force_human_review actually changed this inspection's route (i.e. it
    # would have been PASS/CONFIRMED without it) — lets the audit export and HITL UI show
    # WHY a human was asked to look at an otherwise-routine case.
    mandatory_review_forced: bool
    # Set once at submission time (backend/app/langgraph_api.py's _submitter_name, from the
    # authenticated CurrentUser) — the operator who ran this inspection. Distinct from
    # human_decision.reviewer, which is whoever later resolved a HITL case and is absent for
    # the common case of a run that never needed human review.
    submitted_by: str | None
    execution_trace: Annotated[list[TraceEvent], operator.add]
