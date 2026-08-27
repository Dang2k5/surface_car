from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent.graph.state import QCState

CATALOG_PATH = Path(__file__).resolve().parents[1] / "policies" / "qc_policy_catalog.json"


class PolicyReference(BaseModel):
    id: str
    document_family: str
    revision: str
    section: str
    effective_date: str | None = None
    expiry_date: str | None = None
    document_status: str
    authority: str = "REFERENCE"
    title: str
    scope: str
    url: str


class EvidenceCheck(BaseModel):
    evidence: str
    available: bool


class PolicyWarning(BaseModel):
    code: str
    severity: str
    message: str
    document_id: str | None = None


class PolicyDocumentReview(BaseModel):
    query: dict[str, str]
    roles_completed: list[str]
    matched_document_count: int
    extracted_conditions: list[str]
    evidence_comparison: list[EvidenceCheck]
    missing_data: list[str]
    checklist_status: str
    approved_checklist: list[str]
    proposed_checklist: list[str]
    citations: list[PolicyReference]
    warnings: list[PolicyWarning]


class PolicyDecision(BaseModel):
    policy_id: str
    policy_revision: str
    policy_status: str
    approval_scope: str
    policy_title: str
    action_code: str
    action_label: str
    final_status: str
    test_drive_allowed: bool | None
    human_required: bool
    required_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    required_steps: list[str] = Field(default_factory=list)
    references: list[PolicyReference] = Field(default_factory=list)
    document_review: PolicyDocumentReview
    production_eligible: bool = False


ACTION_LABELS = {
    "MANUAL_VISUAL_REINSPECTION": "Giữ xe lại và thực hiện kiểm tra bằng mắt thủ công mới",
    "SURFACE_DAMAGE_ASSESSMENT_AND_REINSPECT": "Giữ lại để đánh giá bề mặt có kiểm soát và tái kiểm tra có ghi nhận",
    "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT": "Giữ xe lại và chuyển sang bộ phận Sửa chữa thân vỏ để đánh giá kỹ thuật",
    "ISOLATE_FOR_GLASS_REPAIR": "Giữ xe lại và chuyển đi đánh giá hư hỏng kính",
    "ISOLATE_FOR_LIGHTING_REPAIR": "Giữ xe lại và chuyển đi sửa chữa hệ thống đèn",
    "IMMOBILIZE_FOR_TIRE_SERVICE": "Cố định xe và chuyển đi bảo dưỡng lốp",
    "HOLD_FOR_WELD_ENGINEERING_REVIEW": "Giữ lại để kỹ thuật hàn xem xét",
    "HOLD_FOR_VIN_VERIFICATION": "Giữ lại để xác minh VIN có kiểm soát",
}


class PolicyCatalog:
    """Versioned policy catalog backed by public standards and plant-approval guards."""

    def __init__(self, path: Path = CATALOG_PATH) -> None:
        self.path = path
        self.document = json.loads(path.read_text(encoding="utf-8"))
        self.sources = {item["id"]: item for item in self.document["sources"]}

    def public_catalog(self) -> dict[str, Any]:
        return self.document

    def create_source(self, data: dict[str, Any]) -> dict[str, Any]:
        if data["id"] in self.sources:
            raise ValueError(f"Source already exists: {data['id']}")
        self.document["sources"].append(data)
        self.sources[data["id"]] = data
        self._persist()
        return data

    def create_policy(self, data: dict[str, Any]) -> dict[str, Any]:
        if any(item["id"] == data["id"] for item in self.document["policies"]):
            raise ValueError(f"Policy already exists: {data['id']}")
        self.document["policies"].append(data)
        self._persist()
        return data

    def update_policy(self, policy_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        policies = self.document["policies"]
        index = next((i for i, item in enumerate(policies) if item["id"] == policy_id), None)
        if index is None:
            return None
        policies[index] = {**policies[index], **changes}
        self._persist()
        return policies[index]

    def delete_policy(self, policy_id: str) -> bool:
        policies = self.document["policies"]
        remaining = [item for item in policies if item["id"] != policy_id]
        if len(remaining) == len(policies):
            return False
        self.document["policies"] = remaining
        self._persist()
        return True

    def _persist(self) -> None:
        # Write to a sibling temp file first so a crash mid-write can't leave the
        # production policy catalog (read on every inspection) truncated or corrupt.
        tmp_path = self.path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(self.document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        tmp_path.replace(self.path)

    def evaluate(self, state: QCState) -> PolicyDecision:
        human_action = str((state.get("human_decision") or {}).get("action", "")).upper()
        if human_action == "REJECT":
            return self._operator_rejected_defect(state)

        defect_type = str(state.get("defect_type") or "unknown")
        policy = next(
            (
                item
                for item in self.document["policies"]
                if defect_type in item.get("defect_types", [])
                and self._matches_context(item, state)
                # A DRAFT policy (e.g. freshly saved from the Rules UI, or an
                # AI-extracted-but-not-yet-reviewed one) must not silently start
                # deciding real vehicles — fall through to the manual-reinspection
                # fail-safe below until a supervisor flips it to APPROVED.
                and self._is_approved(item)
            ),
            None,
        )
        if policy is None:
            return self._manual_reinspection(state)

        return self._decision_from_policy(policy, state)

    def _is_approved(self, policy: dict[str, Any]) -> bool:
        return str(policy.get("checklist_status") or self.document["status"]) == "APPROVED"

    def evaluate_named(self, policy_id: str, state: QCState) -> PolicyDecision:
        policy = next(
            (item for item in self.document["policies"] if item["id"] == policy_id),
            None,
        )
        if policy is None:
            raise KeyError(f"Unknown policy: {policy_id}")
        return self._decision_from_policy(policy, state)

    def _decision_from_policy(self, policy: dict[str, Any], state: QCState) -> PolicyDecision:
        defect_type = str(state.get("defect_type") or "unknown")

        action_code = policy.get("action_code") or policy.get("action_code_by_defect", {}).get(
            defect_type,
            "MANUAL_VISUAL_REINSPECTION",
        )
        required_evidence = list(policy.get("required_evidence", []))
        provided = self._provided_evidence(state)
        missing = [item for item in required_evidence if item not in provided]
        references = [
            PolicyReference.model_validate(self.sources[source_id])
            for source_id in policy.get("source_ids", [])
            if source_id in self.sources
        ]
        status = str(self.document["status"])
        document_review = self._review_documents(
            policy=policy,
            state=state,
            required_evidence=required_evidence,
            provided_evidence=provided,
            references=references,
        )
        return PolicyDecision(
            policy_id=policy["id"],
            policy_revision=self.document["revision"],
            policy_status=status,
            approval_scope=str(self.document.get("approval_scope") or "UNSPECIFIED"),
            policy_title=policy["title"],
            action_code=action_code,
            action_label=ACTION_LABELS.get(action_code, action_code.replace("_", " ").title()),
            final_status=policy["final_status"],
            test_drive_allowed=policy.get("test_drive_allowed"),
            # Missing evidence becomes an operational checklist, not a second
            # approval gate. Known catalogued defects are decided by the Agent;
            # only an unmapped defect reaches the fail-safe manual policy.
            human_required=bool(policy.get("human_required", False)),
            required_evidence=required_evidence,
            missing_evidence=missing,
            required_steps=list(policy.get("steps", [])),
            references=references,
            document_review=document_review,
            production_eligible=(
                status == "APPROVED"
                and self.document.get("approval_scope") == "PRODUCTION"
                and not missing
                and not any(item.severity == "BLOCKING" for item in document_review.warnings)
            ),
        )

    def _operator_rejected_defect(self, state: QCState) -> PolicyDecision:
        """QC Inspector reviewed the AI-flagged region and rejected it as a false positive.

        There is no separate reinspection sub-state: the vehicle passes immediately
        (PASS/FAIL are the only two terminal outcomes — POLICY_GOVERNANCE.md)."""
        sources = [
            PolicyReference.model_validate(self.sources[source_id])
            for source_id in ("FNS-QC-POLICY-DEMO-2026", "ISO-9001-2015")
            if source_id in self.sources
        ]
        policy = {
            "id": "FNS-QC-REJECTED-001",
            "title": "QC operator rejected the AI-flagged defect",
            "conditions": ["QC Inspector reviewed the flagged region and confirmed no qualifying defect is present"],
            "checklist_status": self.document["status"],
            "steps": ["QC_SIGN_OFF"],
        }
        review = self._review_documents(
            policy=policy,
            state=state,
            required_evidence=["qc_reinspection"],
            provided_evidence=self._provided_evidence(state),
            references=sources,
        )
        return PolicyDecision(
            policy_id="FNS-QC-REJECTED-001",
            policy_revision=self.document["revision"],
            policy_status=self.document["status"],
            approval_scope=str(self.document.get("approval_scope") or "UNSPECIFIED"),
            policy_title="QC operator rejected the AI-flagged defect",
            action_code="PASS_QC_REJECTED_DEFECT_FLAG",
            action_label="QC xác nhận không phải lỗi — cho phép chạy thử",
            final_status="PASS",
            test_drive_allowed=True,
            human_required=False,
            required_evidence=["qc_reinspection"],
            missing_evidence=[],
            required_steps=["QC_SIGN_OFF"],
            references=sources,
            document_review=review,
            production_eligible=False,
        )

    def _manual_reinspection(self, state: QCState) -> PolicyDecision:
        sources = [
            PolicyReference.model_validate(self.sources[source_id])
            for source_id in ("FNS-QC-POLICY-DEMO-2026", "ISO-9001-2015")
            if source_id in self.sources
        ]
        policy = {
            "id": "FNS-MANUAL-001",
            "title": "Fail-safe manual visual reinspection",
            "conditions": ["No context-matched controlled policy could authorize an automated disposition"],
            "checklist_status": self.document["status"],
            "steps": ["CONTAIN_VEHICLE", "RECAPTURE_EVIDENCE", "QC_SIGN_OFF"],
        }
        review = self._review_documents(
            policy=policy,
            state=state,
            required_evidence=["qc_reinspection"],
            provided_evidence=self._provided_evidence(state),
            references=sources,
        )
        return PolicyDecision(
            policy_id="FNS-MANUAL-001",
            policy_revision=self.document["revision"],
            policy_status=self.document["status"],
            approval_scope=str(self.document.get("approval_scope") or "UNSPECIFIED"),
            policy_title="Fail-safe manual visual reinspection",
            action_code="MANUAL_VISUAL_REINSPECTION",
            action_label=ACTION_LABELS["MANUAL_VISUAL_REINSPECTION"],
            final_status="FAIL",
            test_drive_allowed=False,
            human_required=True,
            required_evidence=["qc_reinspection"],
            missing_evidence=["qc_reinspection"],
            required_steps=["CONTAIN_VEHICLE", "RECAPTURE_EVIDENCE", "QC_SIGN_OFF"],
            references=sources,
            document_review=review,
            production_eligible=False,
        )

    @staticmethod
    def _matches_context(policy: dict[str, Any], state: QCState) -> bool:
        applicability = policy.get("applicability", {})
        for state_key, policy_key, unknown in (
            ("vehicle_model", "vehicle_models", "unknown_model"),
        ):
            actual = str(state.get(state_key) or unknown)
            allowed = set(str(item) for item in applicability.get(policy_key, ["*"]))
            if actual != unknown and "*" not in allowed and actual not in allowed:
                return False
        return True

    def _review_documents(
        self,
        *,
        policy: dict[str, Any],
        state: QCState,
        required_evidence: list[str],
        provided_evidence: set[str],
        references: list[PolicyReference],
    ) -> PolicyDocumentReview:
        query = {
            "vehicle_model": str(state.get("vehicle_model") or "unknown_model"),
            "defect_type": str(state.get("defect_type") or "unknown"),
        }
        missing_context = [key for key, value in query.items() if value.startswith("unknown")]
        evidence_comparison = [
            EvidenceCheck(evidence=item, available=item in provided_evidence)
            for item in required_evidence
        ]
        warnings: list[PolicyWarning] = []
        if missing_context:
            warnings.append(
                PolicyWarning(
                    code="POLICY_QUERY_CONTEXT_INCOMPLETE",
                    severity="BLOCKING",
                    message=f"Missing policy lookup context: {', '.join(missing_context)}.",
                )
            )

        controlled_references = [
            reference for reference in references if reference.authority == "CONTROLLED_POLICY"
        ]
        active_by_family: dict[str, set[str]] = {}
        today = datetime.now(UTC).date()
        for reference in controlled_references:
            if reference.document_status not in {"ACTIVE", "APPROVED"}:
                warnings.append(
                    PolicyWarning(
                        code="DOCUMENT_NOT_APPROVED_FOR_PLANT_USE",
                        severity="BLOCKING",
                        message="Document is a reference source, not an approved plant release document.",
                        document_id=reference.id,
                    )
                )
            if not reference.effective_date:
                warnings.append(
                    PolicyWarning(
                        code="EFFECTIVE_DATE_UNCONFIRMED",
                        severity="WARNING",
                        message="Effective date is not registered in the controlled catalog.",
                        document_id=reference.id,
                    )
                )
            if reference.expiry_date and _parse_date(reference.expiry_date) < today:
                warnings.append(
                    PolicyWarning(
                        code="DOCUMENT_EXPIRED",
                        severity="BLOCKING",
                        message=f"Document expired on {reference.expiry_date}.",
                        document_id=reference.id,
                    )
                )
            active_by_family.setdefault(reference.document_family, set()).add(reference.revision)
        if not controlled_references:
            warnings.append(
                PolicyWarning(
                    code="NO_APPROVED_CONTROLLED_DOCUMENT",
                    severity="BLOCKING",
                    message="No approved controlled policy document matched the inspection context.",
                )
            )
        for family, revisions in active_by_family.items():
            if len(revisions) > 1:
                warnings.append(
                    PolicyWarning(
                        code="REVISION_CONFLICT",
                        severity="BLOCKING",
                        message=f"Multiple revisions are matched for {family}: {', '.join(sorted(revisions))}.",
                    )
                )

        checklist_status = str(policy.get("checklist_status") or self.document["status"])
        steps = list(policy.get("steps", []))
        if checklist_status != "APPROVED":
            warnings.append(
                PolicyWarning(
                    code="CHECKLIST_NOT_APPROVED",
                    severity="BLOCKING",
                    message="The matched checklist is a proposal and cannot be presented as plant-approved.",
                )
            )
        return PolicyDocumentReview(
            query=query,
            roles_completed=[
                "RETRIEVE_CONTEXT_MATCHED_DOCUMENTS",
                "EXTRACT_RELEVANT_CONDITIONS",
                "COMPARE_EVIDENCE_TO_POLICY",
                "DETECT_MISSING_DATA",
                "EXPLAIN_DECISION_PLAINLY",
                "PROPOSE_APPROVED_CHECKLIST",
                "CITE_DOCUMENT_METADATA",
                "DETECT_EXPIRY_AND_REVISION_CONFLICTS",
            ],
            matched_document_count=sum(
                reference.document_status in {"ACTIVE", "APPROVED"}
                for reference in controlled_references
            ),
            extracted_conditions=list(policy.get("conditions", [])),
            evidence_comparison=evidence_comparison,
            missing_data=[item.evidence for item in evidence_comparison if not item.available],
            checklist_status=checklist_status,
            approved_checklist=steps if checklist_status == "APPROVED" else [],
            proposed_checklist=steps,
            citations=references,
            warnings=warnings,
        )

    @staticmethod
    def _provided_evidence(state: QCState) -> set[str]:
        evidence = set(str(item) for item in state.get("evidence_tags", []))
        if state.get("vehicle_model") and state.get("vehicle_model") != "unknown_model":
            evidence.add("known_vehicle_model")
        if state.get("human_decision"):
            evidence.add("qc_reinspection")
        measurements = state.get("measurements") or {}
        if measurements:
            evidence.add("defect_extent_measurement")
            evidence.add("geometry_measurement")
        return evidence


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)
