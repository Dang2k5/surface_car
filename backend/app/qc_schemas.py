from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DefectCodeCreate(BaseModel):
    defect_code: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,31}$")
    defect_type: Literal["scratch", "dent"]
    cv_label: Literal["scratch", "dent"]
    defect_family: str = Field(default="", max_length=80)
    display_name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    classification_rule: str = Field(default="QC confirmation required", max_length=1000)
    default_severity: str = Field(default="UNASSESSED", min_length=1, max_length=30)
    measurement_required: bool = False
    active: bool = True

    @field_validator("defect_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("defect_type", "cv_label")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")


class QCDecisionCreate(BaseModel):
    thread_id: str | None = None
    inspection_id: str = Field(min_length=1, max_length=100)
    vehicle_id: str = Field(min_length=1, max_length=100)
    defect_code: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,31}$")
    defect_type: str = Field(min_length=2, max_length=50)
    location: str = Field(min_length=1, max_length=200)
    length_mm: float | None = Field(default=None, ge=0, le=10000)
    severity: str = Field(min_length=1, max_length=30)
    action: Literal["APPROVE", "REJECT", "OVERRIDE"]
    disposition: Literal["PASS", "HOLD", "REWORK", "REINSPECT"]
    reviewer: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=2000)
    notes: str = Field(default="", max_length=4000)

    @field_validator("defect_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("defect_type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")
