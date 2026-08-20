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
    finding_groups: list[dict[str, Any]]
    zone_name: str
    defect_detected: bool
    defect_type: str
    confidence: float
    bbox: dict[str, float] | None
    segmentation_result: dict[str, Any] | None
    visual_measurements: dict[str, float | str]
    detections: list[dict[str, Any]]
    enriched_defects: list[dict[str, Any]]
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
    similar_defect_warning: bool
    evidence_tags: list[str]
    decision: str
    reason: str
    visual_assessment: dict[str, Any] | None
    agent_vision_status: str
    mock_vision_scenario: str
    assessment_route: Literal["PASS", "CONFIRMED", "VERIFY", "HITL"]
    verify_count: int
    verify_result: str
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
    verify_threshold: float
    mock_scenario: str
    execution_trace: Annotated[list[TraceEvent], operator.add]
