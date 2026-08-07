from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class InspectionStatus(str, Enum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"


class DefectType(str, Enum):
    SCRATCH = "scratch"
    DENT = "dent"
    PAINT_DEFECT = "paint_defect"


class YoloBBox(BaseModel):
    x1: float = Field(ge=0)
    y1: float = Field(ge=0)
    x2: float = Field(gt=0)
    y2: float = Field(gt=0)


class YoloDetection(BaseModel):
    class_id: int = Field(ge=0)
    class_name: DefectType
    confidence: float = Field(ge=0, le=1)
    bbox: YoloBBox


class YoloImageResult(BaseModel):
    image_id: str
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    camera_id: str
    model_name: str
    model_version: str
    detections: list[YoloDetection]


class DefectCreate(BaseModel):
    defect_type: DefectType
    class_id: int = Field(default=0, ge=0)
    class_name: DefectType | None = None
    confidence: float = Field(ge=0, le=1)
    camera_id: str = Field(min_length=1, max_length=100)
    bbox: YoloBBox | None = None
    image_width: int = Field(default=1920, gt=0)
    image_height: int = Field(default=1080, gt=0)
    model_name: str = "mock-yolo-qc"
    model_version: str = "mock-1.0"
    location: dict[str, Any] | None = None
    severity_rank: str | None = Field(default=None, min_length=1, max_length=20)


class DefectResponse(DefectCreate):
    id: str


class InspectionCreate(BaseModel):
    vin: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=100)
    station: str = Field(default="FNS", min_length=1, max_length=50)
    defects: list[DefectCreate] = Field(default_factory=list)


class InspectionResponse(BaseModel):
    id: str
    vin: str
    model: str
    station: str
    status: InspectionStatus
    created_at: datetime
    defects: list[DefectResponse] = Field(default_factory=list)


class ClassificationResponse(BaseModel):
    id: str
    inspection_id: str
    defect_id: str
    panel: str
    material: str
    gdt_group: int = Field(ge=1, le=5)
    tolerance_mm: float = Field(ge=0)
    measurement_mm: float = Field(ge=0)
    severity_rank: str
    classification_confidence: float = Field(ge=0, le=1)
    source: str
    is_mock: bool
    created_at: datetime


class DecisionRecommendation(str, Enum):
    PASS = "PASS"
    PLAN_A = "PLAN_A"
    PLAN_B = "PLAN_B"
    HITL_REQUIRED = "HITL_REQUIRED"


class DecisionResponse(BaseModel):
    id: str
    inspection_id: str
    recommendation: DecisionRecommendation
    action: str
    route: str
    reason_codes: list[str]
    explanation: str
    test_drive_allowed: bool
    is_mock: bool
    created_at: datetime


class HITLAction(str, Enum):
    CONFIRM = "CONFIRM"
    OVERRIDE = "OVERRIDE"
    REJECT = "REJECT"


class HITLReviewCreate(BaseModel):
    reviewer: str = Field(min_length=1, max_length=100)
    action: HITLAction
    final_recommendation: DecisionRecommendation | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_review(self) -> "HITLReviewCreate":
        if self.action == HITLAction.OVERRIDE:
            if self.final_recommendation is None:
                raise ValueError("final_recommendation is required for OVERRIDE")
            if not self.reason or not self.reason.strip():
                raise ValueError("reason is required for OVERRIDE")
        if self.action == HITLAction.REJECT and (not self.reason or not self.reason.strip()):
            raise ValueError("reason is required for REJECT")
        return self


class HITLReviewResponse(BaseModel):
    id: str
    inspection_id: str
    decision_id: str
    reviewer: str
    action: HITLAction
    original_recommendation: DecisionRecommendation
    final_recommendation: DecisionRecommendation
    reason: str | None
    created_at: datetime


class WorkflowStatus(str, Enum):
    COMPLETED = "COMPLETED"
    WAITING_FOR_HITL = "WAITING_FOR_HITL"


class WorkflowStep(BaseModel):
    name: str
    status: str
    detail: str


class WorkflowRunResponse(BaseModel):
    id: str
    inspection_id: str
    status: WorkflowStatus
    steps: list[WorkflowStep]
    detections: list[DefectResponse]
    classifications: list[ClassificationResponse]
    decision: DecisionResponse
    hitl_required: bool
    agent_explanation: str | None = None
    agent_explanation_status: str = "NOT_REQUESTED"
    created_at: datetime


class AgentExplainRequest(BaseModel):
    language: Literal["en", "vi"] = "vi"
    question: str | None = Field(default=None, max_length=1000)


class AgentExplainResponse(BaseModel):
    inspection_id: str
    answer: str
    model: str
    language: Literal["en", "vi"]
    source: Literal["llm_explanation"] = "llm_explanation"
