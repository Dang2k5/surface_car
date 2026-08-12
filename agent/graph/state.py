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
    image_url: str
    image_paths: list[str]
    camera_id: str
    panel: str
    defect_detected: bool
    defect_type: str
    confidence: float
    bbox: dict[str, float] | None
    segmentation_result: dict[str, Any] | None
    detections: list[dict[str, Any]]
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
    decision: str
    reason: str
    assessment_route: Literal["PASS", "CONFIRMED", "VERIFY", "HITL"]
    verify_count: int
    verify_result: str
    human_required: bool
    human_decision: dict[str, Any] | None
    recommendation_code: str
    recommendation: str
    final_status: str
    error: str | None
    retry_count: int
    max_retries: int
    auto_pass_enabled: bool
    confirmed_threshold: float
    verify_threshold: float
    mock_scenario: str
    execution_trace: Annotated[list[TraceEvent], operator.add]
