from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel

from agent.graph.state import QCState
from agent.services.policy import PolicyDecision

logger = logging.getLogger(__name__)

class ReasoningPayload(BaseModel):
    summary_en: str
    summary_vi: str
    risk_flags: list[str]
    recommended_checks: list[str]
    cited_source_ids: list[str]


class ReasoningAnalysis(ReasoningPayload):
    provider: str
    model: str
    fallback_reason: str | None = None


class DefectCodeClassification(BaseModel):
    defect_code: str | None
    defect_family: str | None
    confidence: float
    rationale_vi: str
    candidate_codes: list[str]
    similar_observation_warning: bool = False
    provider: str
    model: str
    fallback_reason: str | None = None


class ReasoningService(Protocol):
    def analyze(self, state: QCState, policy: PolicyDecision) -> ReasoningAnalysis: ...

    def classify_defect_code(
        self, state: QCState, candidates: list[dict[str, object]]
    ) -> DefectCodeClassification: ...

    def runtime_status(self) -> dict[str, object]: ...


class DeterministicReasoningService:
    """Auditable fallback that never invents measurements or acceptance limits."""

    def runtime_status(self) -> dict[str, object]:
        return {
            "mode": "RULE_BASED",
            "provider": "deterministic",
            "configured": True,
            "llm_accessed": False,
            "last_call_status": "NOT_APPLICABLE",
            "last_success_at": None,
            "last_error": None,
        }

    def classify_defect_code(
        self, state: QCState, candidates: list[dict[str, object]]
    ) -> DefectCodeClassification:
        codes = [str(item.get("defect_code")) for item in candidates]
        if not candidates:
            return DefectCodeClassification(
                defect_code=None,
                defect_family=None,
                confidence=0.0,
                rationale_vi="Không có mã QC đang hoạt động phù hợp với label CV.",
                candidate_codes=[],
                provider="deterministic",
                model="catalog-rule-v1",
            )
        defect_type = str(state.get("defect_type") or "")
        detections = [
            item for item in state.get("detections", [])
            if item.get("class_name") == defect_type
        ]
        visual = state.get("visual_measurements") or {}
        width_mm = visual.get("estimated_width_mm")
        width = float(width_mm) if width_mm is not None else None
        position = str(visual.get("relative_position") or "")
        bbox = state.get("bbox") or {}
        box_width = max(0.0, float(bbox.get("x2", 0)) - float(bbox.get("x1", 0)))
        box_height = max(1.0, float(bbox.get("y2", 0)) - float(bbox.get("y1", 0)))
        code = None
        reason = ""
        if len(detections) >= 2:
            code = "SCRATCH04" if defect_type == "scratch" else "DENT05"
            reason = f"Phát hiện {len(detections)} vùng lỗi cùng loại trong một inspection."
        elif defect_type == "scratch" and (position.endswith("_left") or position.endswith("_right")):
            code = "SCRATCH05"
            reason = "Vùng lỗi nằm gần mép trái/phải; Agent phân loại là lỗi vùng mép."
        elif defect_type == "dent" and box_width / box_height >= 2:
            code = "DENT04"
            reason = "Vùng móp có tỷ lệ dài/rộng lớn; gợi ý kiểm tra nếp gấp."
        elif width is not None:
            if defect_type == "scratch":
                code = "SCRATCH01" if width <= 50 else "SCRATCH02" if width <= 150 else "SCRATCH03"
            elif defect_type == "dent":
                code = "DENT01" if width <= 50 else "DENT02" if width <= 150 else "DENT03"
            reason = f"Phân loại theo bề rộng ước lượng pilot {width:.1f} mm."
        if code not in codes:
            code = codes[0]
            reason = "Agent chọn mã mặc định hợp lệ của nhóm lỗi theo danh mục QC hiện hành."
        selected = next(item for item in candidates if item.get("defect_code") == code)
        return DefectCodeClassification(
            defect_code=code,
            defect_family=str(selected.get("defect_family") or defect_type.upper()),
            confidence=0.98 if width is not None or len(detections) >= 2 else 0.95,
            rationale_vi=reason,
            candidate_codes=codes,
            similar_observation_warning=len(detections) >= 2,
            provider="deterministic",
            model="catalog-rule-v1",
        )

    def analyze(self, state: QCState, policy: PolicyDecision) -> ReasoningAnalysis:
        defect = state.get("defect_type", "unknown")
        confidence = float(state.get("confidence", 0.0))
        missing = policy.missing_evidence
        catalog_matches = state.get("suggested_defect_codes") or []
        selected_code = str(state.get("classified_defect_code") or "UNMAPPED")
        selected = next(
            (item for item in catalog_matches if item.get("defect_code") == selected_code),
            {},
        )
        defect_class = str(selected.get("display_name") or state.get("defect_family") or defect)
        severity = str(state.get("severity") or "UNASSESSED")
        visual = state.get("visual_measurements") or {}
        length_mm = visual.get("estimated_length_mm")
        width_mm = visual.get("estimated_width_mm")
        height_mm = visual.get("estimated_height_mm")
        position = str(visual.get("relative_position") or state.get("zone_name") or "unknown")
        size_en = (
            f"estimated {float(length_mm):.1f} mm long "
            f"({float(width_mm or 0):.1f} × {float(height_mm or 0):.1f} mm)"
            if length_mm is not None
            else "physical size unavailable"
        )
        size_vi = (
            f"dài ước lượng {float(length_mm):.1f} mm "
            f"({float(width_mm or 0):.1f} × {float(height_mm or 0):.1f} mm)"
            if length_mm is not None
            else "chưa có kích thước vật lý"
        )
        scope_note_en = (
            "The policy is approved for production use."
            if policy.approval_scope == "PRODUCTION"
            else "The policy is approved for demo workflow validation only, not production release."
        )
        summary_en = (
            f"Evidence: {defect} at {confidence:.0%}, {size_en}, at {position.replace('_', ' ')}. "
            f"Classification: {selected_code} — {defect_class}, impact level {severity}. "
            f"Policy: {policy.policy_id}, revision {policy.policy_revision}, selects {policy.action_label}. "
            f"Decision: {policy.final_status}; test drive "
            f"{'allowed' if policy.test_drive_allowed else 'blocked'}. {scope_note_en}"
        )
        defect_vi = {"scratch": "vết xước", "dent": "vết móp"}.get(defect, defect)
        summary_vi = (
            f"Evidence: CV phát hiện {defect_vi} tại {position.replace('_', ' ')}, {size_vi}. "
            f"Phân loại: Agent xác định mã {selected_code} — {defect_class}, mức ảnh hưởng {severity}. "
            f"Đối chiếu policy: {policy.policy_id}, revision {policy.policy_revision}. "
            f"Quyết định: {policy.action_label}; trạng thái {policy.final_status}; "
            f"{'cho phép' if policy.test_drive_allowed else 'khóa'} test drive."
        )
        risk_flags = []
        if policy.policy_status != "APPROVED":
            risk_flags.append("POLICY_NOT_PLANT_APPROVED")
        if policy.approval_scope != "PRODUCTION":
            risk_flags.append("DEMO_APPROVAL_NOT_PRODUCTION_RELEASE")
        if missing:
            risk_flags.append("MISSING_REQUIRED_EVIDENCE")
        if state.get("severity") in {None, "UNASSESSED", "UNCONFIRMED"}:
            risk_flags.append("SEVERITY_NOT_ASSESSED")
        return ReasoningAnalysis(
            summary_en=summary_en,
            summary_vi=summary_vi,
            risk_flags=risk_flags,
            recommended_checks=missing or ["qc_signoff"],
            cited_source_ids=[item.id for item in policy.references],
            provider="deterministic",
            model="policy-template-v1",
        )


class GroqReasoningService:
    """Constrained Groq copilot; deterministic policy remains authoritative."""

    def __init__(self, *, api_key: str, model: str, fallback: ReasoningService | None = None) -> None:
        from groq import Groq

        self.client = Groq(api_key=api_key)
        self.model = model
        self.fallback = fallback or DeterministicReasoningService()
        self.last_call_status = "NOT_CALLED"
        self.last_success_at: str | None = None
        self.last_error: str | None = None

    def runtime_status(self) -> dict[str, object]:
        return {
            "mode": "LLM_WITH_RULE_FALLBACK",
            "provider": "groq",
            "model": self.model,
            "configured": True,
            "llm_accessed": self.last_success_at is not None,
            "last_call_status": self.last_call_status,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
        }

    def _mark_success(self) -> None:
        self.last_call_status = "SUCCESS"
        self.last_success_at = datetime.now(UTC).isoformat()
        self.last_error = None

    def _mark_failure(self, error: Exception) -> None:
        self.last_call_status = "FAILED_USING_RULE_FALLBACK"
        self.last_error = type(error).__name__

    def classify_defect_code(
        self, state: QCState, candidates: list[dict[str, object]]
    ) -> DefectCodeClassification:
        fallback = self.fallback.classify_defect_code(state, candidates)
        if not candidates:
            return fallback
        allowed = {str(item.get("defect_code")) for item in candidates}
        prompt = {
            "task": "Select exactly one approved QC defect code for this CV finding.",
            "evidence": {
                "defect_type": state.get("defect_type"),
                "confidence": state.get("confidence"),
                "zone_name": state.get("zone_name"),
                "visual_measurements": state.get("visual_measurements"),
                "detections": state.get("detections"),
            },
            "allowed_codes": candidates,
            "constraints": [
                "Return a defect_code only from allowed_codes.",
                "Do not invent measurements or defect codes.",
                "Use Vietnamese for rationale_vi.",
                "Set similar_observation_warning when at least two similar detections occur.",
            ],
        }
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {"role": "system", "content": "You are a constrained automotive QC code classifier. Return JSON only."},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
            )
            payload = json.loads(completion.choices[0].message.content or "{}")
            if str(payload.get("defect_code")) not in allowed:
                raise ValueError("Classifier selected a code outside the active catalog")
            selected = next(item for item in candidates if item.get("defect_code") == payload["defect_code"])
            self._mark_success()
            return DefectCodeClassification(
                defect_code=str(payload["defect_code"]),
                defect_family=str(selected.get("defect_family") or ""),
                confidence=float(payload.get("confidence", 0.7)),
                rationale_vi=str(payload.get("rationale_vi") or "LLM phân loại theo evidence CV và rule danh mục."),
                candidate_codes=sorted(allowed),
                similar_observation_warning=bool(payload.get("similar_observation_warning", False)),
                provider="groq",
                model=self.model,
            )
        except Exception as exc:
            self._mark_failure(exc)
            logger.warning("Groq code classification unavailable; using deterministic fallback: %s", exc)
            return fallback.model_copy(update={"fallback_reason": type(exc).__name__})

    def analyze(self, state: QCState, policy: PolicyDecision) -> ReasoningAnalysis:
        prompt = {
            "task": "Explain the policy outcome and identify missing evidence. Do not change the action code, final status, release permission, measurements, or citations.",
            "inspection": {
                "defect_type": state.get("defect_type"),
                "classified_defect_code": state.get("classified_defect_code"),
                "defect_family": state.get("defect_family"),
                "confidence": state.get("confidence"),
                "zone_name": state.get("zone_name"),
                "camera_id": state.get("camera_id"),
                "bbox": state.get("bbox"),
                "visual_measurements": state.get("visual_measurements"),
                "severity": state.get("severity"),
                "verify_result": state.get("verify_result"),
                "similar_defect_warning": state.get("similar_defect_warning"),
            },
            "authoritative_policy_result": policy.model_dump(mode="json"),
            "constraints": [
                "Never invent a measurement or acceptance threshold.",
                "Only cite source IDs included in authoritative_policy_result.references.",
                "Explain the exact policy status and approval scope; demo approval is not production release authority.",
                "Return concise Vietnamese and English summaries.",
                "Explain the selected defect code, confidence, estimated length, location, action plan, and warnings when present.",
            ],
        }
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a Visual QC reasoning copilot. Policy output is immutable. Return only the requested JSON schema.",
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "visual_qc_reasoning",
                        "strict": False,
                        "schema": ReasoningPayload.model_json_schema(),
                    },
                },
            )
            content = completion.choices[0].message.content or "{}"
            payload = ReasoningPayload.model_validate_json(content)
            allowed_sources = {item.id for item in policy.references}
            if not set(payload.cited_source_ids).issubset(allowed_sources):
                raise ValueError("Groq returned a citation outside the approved policy context")
            self._mark_success()
            return ReasoningAnalysis(
                **payload.model_dump(),
                provider="groq",
                model=self.model,
            )
        except Exception as exc:  # fail closed to deterministic explanation
            self._mark_failure(exc)
            logger.warning("Groq reasoning unavailable; using deterministic fallback: %s", exc)
            result = self.fallback.analyze(state, policy)
            return result.model_copy(update={"fallback_reason": type(exc).__name__})
