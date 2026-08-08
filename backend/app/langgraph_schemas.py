from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class LangGraphInspectionCreate(BaseModel):
    inspection_id: str | None = None
    vehicle_id: str = Field(min_length=1, max_length=32)
    image_url: str | None = None
    image_paths: list[str] = Field(default_factory=list)
    camera_id: str = Field(default="cam-fns-01", min_length=1, max_length=100)
    panel: str = Field(default="unknown_panel", min_length=1, max_length=100)
    mock_scenario: Literal[
        "no_defect",
        "high_confidence",
        "medium_confirmed",
        "verify_uncertain",
        "low_confidence",
    ] = "high_confidence"
    mock_detection: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_image_input(self) -> LangGraphInspectionCreate:
        if not self.image_url and not self.image_paths:
            raise ValueError("image_url or image_paths is required")
        return self


class LangGraphResumeRequest(BaseModel):
    action: Literal["APPROVE", "REJECT", "OVERRIDE"]
    reviewer: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    recommendation: str | None = Field(default=None, max_length=200)

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
