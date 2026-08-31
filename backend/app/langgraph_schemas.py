from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class LangGraphInspectionCreate(BaseModel):
    inspection_id: str | None = None
    vehicle_id: str = Field(min_length=1, max_length=32)
    vehicle_model: str = Field(default="unknown_model", min_length=1, max_length=100)
    lot_id: str | None = Field(default=None, max_length=100)
    shift_id: str | None = Field(default=None, max_length=100)
    production_date: str | None = Field(default=None, max_length=10)
    station_id: str = Field(default="FNS_LINE_HA_01", min_length=1, max_length=100)
    image_url: str | None = None
    image_paths: list[str] = Field(default_factory=list)
    camera_id: str = Field(default="cam-fns-01", min_length=1, max_length=100)
    zone_name: str = Field(default="unknown_zone", min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_image_input(self) -> LangGraphInspectionCreate:
        if not self.image_url and not self.image_paths:
            raise ValueError("image_url or image_paths is required")
        return self


class DetectionResolution(BaseModel):
    """One operator decision for ONE unresolved finding (QCState.camera_classifications
    entry with classified_defect_code == None). Required whenever a HITL case has more than
    one such finding -- see LangGraphResumeRequest.validate_resolutions -- so an operator
    resolving a case with, say, one real scratch AND one real dent must pick a code for
    EACH, instead of the single `defect_code` field being applied to both."""

    detection_id: str = Field(min_length=1, max_length=100)
    defect_code: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,31}$")
    severity: str | None = Field(default=None, max_length=30)


class LangGraphResumeRequest(BaseModel):
    # Not a Literal: the first HITL gate (human_review) only ever sends APPROVE/REJECT/OVERRIDE,
    # but the second gate (supervisor_review) sends either UPHOLD_POLICY or the id of whichever
    # APPROVED catalog policy the supervisor chose to apply — an open-ended, catalog-driven set
    # the HTTP layer can't enumerate. Each graph node validates its own allowed values and raises
    # ValueError (-> HTTP 422) for anything else; this schema only bounds the string's shape.
    action: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_:-]*$")
    reviewer: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    recommendation: str | None = Field(default=None, max_length=200)
    # Single-finding shortcut: still accepted, and still the only field the frontend needs to
    # send when a case has at most one unresolved finding. Ignored (backend/app/
    # langgraph_api.py's resume_langgraph_inspection) once `detection_resolutions` is given.
    defect_code: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,31}$")
    severity: str | None = Field(default=None, max_length=30)
    location: str | None = Field(default=None, max_length=200)
    length_mm: float | None = Field(default=None, ge=0, le=10000)
    disposition: Literal["PASS", "HOLD", "REPAIR"] | None = None
    notes: str = Field(default="", max_length=4000)
    # Required instead of `defect_code` when the case has MORE than one unresolved finding
    # (agent/graph/nodes.py's QCNodes.detect_defect: several independent detections can each
    # need HITL) -- one entry per unresolved detection_id, each with its own defect_code.
    detection_resolutions: list[DetectionResolution] | None = None

    @model_validator(mode="after")
    def validate_override(self) -> LangGraphResumeRequest:
        if self.action == "OVERRIDE" and not self.recommendation:
            raise ValueError("recommendation is required for OVERRIDE")
        return self


class LangGraphRunResponse(BaseModel):
    thread_id: str
    status: Literal["COMPLETED", "INTERRUPTED"]
    state: dict[str, Any]
    interrupt: dict[str, Any] | None = None


class AgentGraphResponse(BaseModel):
    mermaid: str
    nodes: list[str]
    checkpointer: str
