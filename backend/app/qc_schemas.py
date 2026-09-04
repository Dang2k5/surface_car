from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


RuleType = Literal["THRESHOLD_MM", "MIN_COUNT", "REQUIRES_HUMAN"]


def _check_rule_fields(
    rule_type: str | None, min_mm: float | None, max_mm: float | None, min_detection_count: int | None
) -> None:
    """Shared consistency guard for the structured, machine-evaluable classification rule
    (agent/services/defect_rule_engine.py) -- kept separate from the free-text
    `classification_rule` field, which stays whatever a human wrote for display. A code
    with no `rule_type` (or an inconsistent one) is deliberately left unable to auto-match
    in the rule engine, which routes it to HITL rather than guessing -- but we still reject
    obviously-inconsistent data at write time so nobody expects a rule that was never
    actually saved correctly."""
    if rule_type == "THRESHOLD_MM":
        if min_mm is None and max_mm is None:
            raise ValueError("THRESHOLD_MM requires at least one of min_mm or max_mm")
        if min_detection_count is not None:
            raise ValueError("min_detection_count is only valid with rule_type=MIN_COUNT")
    elif rule_type == "MIN_COUNT":
        if min_detection_count is None:
            raise ValueError("MIN_COUNT requires min_detection_count")
        if min_mm is not None or max_mm is not None:
            raise ValueError("min_mm/max_mm are only valid with rule_type=THRESHOLD_MM")
    elif rule_type in (None, "REQUIRES_HUMAN"):
        if min_mm is not None or max_mm is not None or min_detection_count is not None:
            raise ValueError(
                "min_mm/max_mm/min_detection_count require rule_type=THRESHOLD_MM or MIN_COUNT"
            )


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
    # Traces which controlled-policy source (the policy_sources table, backend/app/database.py)
    # justifies default_severity/classification_rule — e.g. the mm bands SCRATCH01-05/DENT01-05
    # ship with cite "FNS-SEVERITY-CRITERIA-INTERNAL" (DRAFT). Not a DB-level foreign key:
    # policy_sources is a separate table (agent/services/policy.py's PolicyCatalog owns it),
    # not one this defect_catalog row references directly.
    source_id: str | None = Field(default=None, max_length=64)
    # Structured rule the deterministic rule engine evaluates automatically -- see
    # agent/services/defect_rule_engine.py. Left unset (None), a code can never auto-match
    # and every finding classified against it routes straight to HITL.
    rule_type: RuleType | None = None
    min_mm: float | None = Field(default=None, ge=0)
    max_mm: float | None = Field(default=None, ge=0)
    min_detection_count: int | None = Field(default=None, ge=1)

    @field_validator("defect_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("defect_type", "cv_label")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")

    @model_validator(mode="after")
    def validate_rule_fields(self) -> DefectCodeCreate:
        _check_rule_fields(self.rule_type, self.min_mm, self.max_mm, self.min_detection_count)
        return self


class DefectCodeUpdate(BaseModel):
    defect_family: str | None = Field(default=None, max_length=80)
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    classification_rule: str | None = Field(default=None, max_length=1000)
    default_severity: str | None = Field(default=None, min_length=1, max_length=30)
    measurement_required: bool | None = None
    source_id: str | None = Field(default=None, max_length=64)
    active: bool | None = None
    rule_type: RuleType | None = None
    min_mm: float | None = Field(default=None, ge=0)
    max_mm: float | None = Field(default=None, ge=0)
    min_detection_count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_rule_fields(self) -> DefectCodeUpdate:
        # Only enforced when `rule_type` is part of THIS update -- a partial patch that
        # only touches e.g. `display_name` must not be forced to re-supply min_mm/max_mm
        # that were already saved in an earlier update.
        if self.rule_type is not None:
            _check_rule_fields(self.rule_type, self.min_mm, self.max_mm, self.min_detection_count)
        return self


class ProfileUpdate(BaseModel):
    role: Literal["QC_OPERATOR", "QC_SUPERVISOR"] | None = None
    station_id: str | None = None
    active: bool | None = None


class ShiftCreate(BaseModel):
    shift_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{1,31}$")
    name: str = Field(min_length=1, max_length=80)
    start_time: str = Field(default="", max_length=16)
    end_time: str = Field(default="", max_length=16)
    active: bool = True

    @field_validator("shift_id")
    @classmethod
    def normalize_shift_id(cls, value: str) -> str:
        return value.strip().upper()


class ShiftUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    start_time: str | None = Field(default=None, max_length=16)
    end_time: str | None = Field(default=None, max_length=16)
    active: bool | None = None


class LotCreate(BaseModel):
    lot_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,63}$")
    name: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=500)
    # A lot is produced during one shift, at one station (API_CONTRACT.md relationship: Trạm/Ca
    # are independent catalogs, Lô references the specific Trạm+Ca it was produced under).
    station_id: str = Field(min_length=1, max_length=64)
    shift_id: str = Field(min_length=1, max_length=32)
    # Default model used to pre-fill the Inspector's "Model sản phẩm" field and to generate
    # product codes (<Mã Lô>-<Model sản phẩm>-<STT>) — see Database.allocate_lot_product.
    # It's a default, not immutable: an inspection can still submit a different model.
    product_model: str = Field(min_length=1, max_length=100)
    # Caps how many product codes can be allocated to this lot (see Database.allocate_lot_product).
    quantity: int = Field(ge=1, le=9999)
    active: bool = True

    @field_validator("lot_id")
    @classmethod
    def normalize_lot_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("product_model")
    @classmethod
    def normalize_product_model(cls, value: str) -> str:
        return value.strip()

    @field_validator("station_id")
    @classmethod
    def normalize_station_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("shift_id")
    @classmethod
    def normalize_shift_id(cls, value: str) -> str:
        return value.strip().upper()


class LotUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)
    station_id: str | None = Field(default=None, min_length=1, max_length=64)
    shift_id: str | None = Field(default=None, min_length=1, max_length=32)
    product_model: str | None = Field(default=None, min_length=1, max_length=100)
    # Quantity may only be increased — decreasing below the number of product codes already
    # allocated to this lot would orphan those codes.
    quantity: int | None = Field(default=None, ge=1, le=9999)
    active: bool | None = None


class LotProductAllocate(BaseModel):
    """Allocates the next sequential product code for a lot: <Mã Lô>-<Model sản phẩm>-<STT>."""

    vehicle_model: str = Field(min_length=1, max_length=100)

    @field_validator("vehicle_model")
    @classmethod
    def normalize_vehicle_model(cls, value: str) -> str:
        return value.strip()


class StationCreate(BaseModel):
    station_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    active: bool = True

    @field_validator("station_id")
    @classmethod
    def normalize_station_id(cls, value: str) -> str:
        return value.strip()


class StationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None


class PolicyApplicability(BaseModel):
    vehicle_models: list[str] = Field(default_factory=lambda: ["*"])


class PolicyItemCreate(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,63}$")
    title: str = Field(min_length=1, max_length=200)
    applicability: PolicyApplicability = Field(default_factory=PolicyApplicability)
    conditions: list[str] = Field(default_factory=list)
    checklist_status: Literal["DRAFT", "APPROVED"] = "DRAFT"
    defect_types: list[str] = Field(min_length=1)
    # Optional finer-grained gate on top of defect_types -- when set, this policy only
    # governs findings classified to one of these specific defect_catalog codes (e.g.
    # DENT02/DENT03) instead of every finding of the selected defect_types. Left empty/unset,
    # the policy is unrestricted within its defect_types, exactly as before this field existed
    # (agent/services/policy.py's PolicyCatalog._matches_defect_code).
    defect_codes: list[str] | None = None
    action_code: str | None = None
    action_code_by_defect: dict[str, str] | None = None
    final_status: str = Field(min_length=1, max_length=60)
    test_drive_allowed: bool | None = None
    human_required: bool = False
    required_evidence: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def require_action_mapping(self) -> "PolicyItemCreate":
        if not self.action_code and not self.action_code_by_defect:
            raise ValueError("Either action_code or action_code_by_defect is required")
        return self


class PolicySourceCreate(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,63}$")
    document_family: str = Field(min_length=1, max_length=80)
    revision: str = Field(min_length=1, max_length=40)
    section: str = Field(min_length=1, max_length=200)
    effective_date: str | None = None
    expiry_date: str | None = None
    document_status: str = "DRAFT"
    authority: str = "REFERENCE"
    title: str = Field(min_length=1, max_length=200)
    scope: str = Field(min_length=1, max_length=2000)
    # Set by the server from the uploaded file (policy_extract_api.create_source),
    # never accepted from the client — a source always points at a file this backend
    # actually stored, not an arbitrary client-supplied URL.
    url: str = Field(default="", max_length=500)

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        return value.strip().upper()


class PolicyItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    applicability: PolicyApplicability | None = None
    conditions: list[str] | None = None
    checklist_status: Literal["DRAFT", "APPROVED"] | None = None
    defect_types: list[str] | None = Field(default=None, min_length=1)
    defect_codes: list[str] | None = None
    action_code: str | None = None
    action_code_by_defect: dict[str, str] | None = None
    final_status: str | None = Field(default=None, min_length=1, max_length=60)
    test_drive_allowed: bool | None = None
    human_required: bool | None = None
    required_evidence: list[str] | None = None
    steps: list[str] | None = None
    source_ids: list[str] | None = None


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
    disposition: Literal["PASS", "HOLD", "REPAIR"]
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
