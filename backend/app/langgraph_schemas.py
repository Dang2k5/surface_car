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


class LangGraphResumeRequest(BaseModel):
    action: Literal["APPROVE", "REJECT", "OVERRIDE"]
    reviewer: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    recommendation: str | None = Field(default=None, max_length=200)
    defect_code: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,31}$")
    severity: str | None = Field(default=None, max_length=30)
    location: str | None = Field(default=None, max_length=200)
    length_mm: float | None = Field(default=None, ge=0, le=10000)
    disposition: Literal["PASS", "HOLD", "REPAIR"] | None = None
    notes: str = Field(default="", max_length=4000)

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
