from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel

from agent.graph.state import QCState
from agent.services.policy import PolicyDecision
from agent.services.policy_extractor import PolicyDraft, PolicyExtractionResult, PolicySourceDraft

logger = logging.getLogger(__name__)

class ReasoningPayload(BaseModel):
    summary_en: str
    summary_vi: str
    risk_flags: list[str]
    recommended_checks: list[str]
    cited_source_ids: list[str]


class ReasoningAnalysis(ReasoningPayload):
    provider: str = "groq"
    model: str = ""
    severity: str
    action_code: str
    action_label: str
    final_status: str
    allow_test_drive: bool
    decision_rationale_vi: str
    fallback_reason: str | None = None


class ReasoningUnavailableError(RuntimeError):
    """Raised when the configured LLM Agent cannot produce a validated decision."""


def _detections_for_prompt(state: QCState) -> list[dict[str, object]]:
    """Strip segmentation polygons out of `detections` before it goes into an LLM
    prompt: the classifier only reasons about class/confidence/measurements/camera,
    never the raw mask shape, and a 128-point polygon per detection is the single
    biggest token cost in this prompt (it alone has pushed real inspections over
    Groq's per-minute token limit, e.g. 8712 tokens against an 8000 TPM cap)."""
    return [
        {key: value for key, value in detection.items() if key != "segmentation"}
        for detection in state.get("detections", [])
    ]


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

    def extract_policy_draft(
        self, *, document_text: str, filename: str, known_vocabulary: dict[str, list[str]]
    ) -> PolicyExtractionResult: ...

    def runtime_status(self) -> dict[str, object]: ...


class DeterministicReasoningService:
    """Rule-based narrative generator.

    Used directly when QC_REASONING_PROVIDER != groq (tests), and reused by
    agent/graph/nodes.py as the fallback narrative source when GroqReasoningService.analyze
    raises ReasoningUnavailableError -- the PASS/FAIL/HITL decision is already final by that
    point (deterministic policy evaluation), so this only ever supplies the explanatory text,
    never a decision of its own."""

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
            # Bands mirror defect_catalog's classification_rule (Japan auction-sheet
            # A1/A2/A3 scratch grading; PDR dent-diameter reference chart for dent) —
            # see agent/services/defect_catalog.py and docs/POLICY_GOVERNANCE.md.
            if defect_type == "scratch":
                code = "SCRATCH01" if width <= 50 else "SCRATCH02" if width <= 100 else "SCRATCH03"
            elif defect_type == "dent":
                code = "DENT01" if width <= 25 else "DENT02" if width <= 50 else "DENT03"
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

    def extract_policy_draft(
        self, *, document_text: str, filename: str, known_vocabulary: dict[str, list[str]]
    ) -> PolicyExtractionResult:
        """Keyword-only heuristic — enough to exercise the upload/extract endpoint in
        tests without a real LLM. Never used at runtime (QC_REASONING_PROVIDER=groq)."""
        lowered = document_text.lower()
        defect_types = []
        if "xước" in lowered or "scratch" in lowered:
            defect_types.append("scratch")
        if "móp" in lowered or "dent" in lowered:
            defect_types.append("dent")
        if not defect_types:
            defect_types = ["scratch"]
        return PolicyExtractionResult(
            policy=PolicyDraft(
                suggested_id="FNS-DRAFT-001",
                title=f"Chính sách nháp trích xuất từ {filename}",
                defect_types=defect_types,
                conditions=["Trích xuất tự động — QC Trưởng cần rà soát lại toàn bộ trước khi duyệt"],
                required_evidence=["qc_reinspection"],
                steps=["QC_SIGN_OFF"],
                action_code="MANUAL_VISUAL_REINSPECTION",
                final_status="FAIL",
                test_drive_allowed=False,
                human_required=True,
            ),
            source=PolicySourceDraft(
                document_family="UNCLASSIFIED",
                revision="draft",
                title=filename,
                section="Toàn bộ tài liệu",
            ),
            extraction_notes_vi="Kết quả từ deterministic fallback (không dùng LLM) — chỉ dùng cho test.",
            provider="deterministic",
            model="policy-extract-heuristic-v1",
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
        # The severity A/B/C threshold itself is cited from defect_catalog's own source
        # (severity_source_id, set only once defect_catalog confirmed a defect_code — see
        # agent/graph/nodes.py's detect_defect), on top of whatever the matched policy cites.
        cited_source_ids = [item.id for item in policy.references]
        severity_source_id = state.get("severity_source_id")
        if severity_source_id and severity_source_id not in cited_source_ids:
            cited_source_ids.append(severity_source_id)
        return ReasoningAnalysis(
            summary_en=summary_en,
            summary_vi=summary_vi,
            risk_flags=risk_flags,
            recommended_checks=missing or ["qc_signoff"],
            cited_source_ids=cited_source_ids,
            provider="deterministic",
            model="policy-template-v1",
            severity=str(state.get("severity") or "UNASSESSED"),
            action_code=policy.action_code,
            action_label=policy.action_label,
            final_status=policy.final_status,
            allow_test_drive=bool(policy.test_drive_allowed),
            decision_rationale_vi=summary_vi,
        )


class UnavailableReasoningService:
    """Used when LLM mode is requested (QC_REASONING_PROVIDER=groq) without a usable key.

    Every method raises ReasoningUnavailableError -- for `analyze()` that is no longer
    fail-closed on the decision (agent/graph/nodes.py catches it and falls back to
    DeterministicReasoningService, keeping the policy-driven route/final_status unchanged),
    only the narrative degrades. `classify_defect_code` has no production caller anymore
    (agent/graph/nodes.py uses agent/services/defect_rule_engine.py instead); this Protocol
    method is kept for interface parity across providers and direct unit-testing, not for a
    live call path. `extract_policy_draft` (policy-extraction endpoint) has no fallback and
    still fails closed on this raise."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def runtime_status(self) -> dict[str, object]:
        return {
            "mode": "LLM_REQUIRED",
            "provider": "groq",
            "configured": False,
            "llm_accessed": False,
            "last_call_status": "UNAVAILABLE",
            "last_success_at": None,
            "last_error": self.reason,
        }

    def classify_defect_code(
        self, state: QCState, candidates: list[dict[str, object]]
    ) -> DefectCodeClassification:
        raise ReasoningUnavailableError(self.reason)

    def extract_policy_draft(
        self, *, document_text: str, filename: str, known_vocabulary: dict[str, list[str]]
    ) -> PolicyExtractionResult:
        raise ReasoningUnavailableError(self.reason)

    def analyze(self, state: QCState, policy: PolicyDecision) -> ReasoningAnalysis:
        raise ReasoningUnavailableError(self.reason)


class GroqReasoningService:
    """LLM decision service constrained by catalog, evidence and policy guards."""

    def __init__(self, *, api_key: str, model: str, timeout: float = 8.0) -> None:
        from groq import Groq

        # A short, explicit timeout is safe here: agent/graph/nodes.py never lets a
        # narrative failure change the PASS/FAIL/HITL decision or crash the request (it
        # falls back to DeterministicReasoningService), so failing fast just means losing
        # the LLM narrative sooner instead of hanging the request on the SDK's ~60s default.
        self.client = Groq(api_key=api_key, timeout=timeout)
        self.model = model
        self.last_call_status = "NOT_CALLED"
        self.last_success_at: str | None = None
        self.last_error: str | None = None

    def runtime_status(self) -> dict[str, object]:
        return {
            "mode": "LLM_AGENT",
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
        self.last_call_status = "FAILED_REQUIRES_HITL"
        self.last_error = type(error).__name__

    def classify_defect_code(
        self, state: QCState, candidates: list[dict[str, object]]
    ) -> DefectCodeClassification:
        if not candidates:
            raise ReasoningUnavailableError("No approved defect-code candidate matches the CV label")
        allowed = {str(item.get("defect_code")) for item in candidates}
        prompt = {
            "task": "Select exactly one approved QC defect code for this CV finding.",
            "evidence": {
                "defect_type": state.get("defect_type"),
                "confidence": state.get("confidence"),
                "zone_name": state.get("zone_name"),
                "visual_measurements": state.get("visual_measurements"),
                "detections": _detections_for_prompt(state),
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
            logger.warning("Groq code classification failed; HITL is required: %s", exc)
            raise ReasoningUnavailableError(type(exc).__name__) from exc

    def extract_policy_draft(
        self, *, document_text: str, filename: str, known_vocabulary: dict[str, list[str]]
    ) -> PolicyExtractionResult:
        # Groq context windows are finite; a scanned/huge control plan is truncated
        # rather than rejected outright — the supervisor still reviews every field.
        truncated_text = document_text[:20000]
        prompt = {
            "task": (
                "Read this QC work-instruction / control-plan document and draft ONE candidate "
                "policy for the visual QC catalog, plus the document metadata needed to register it "
                "as a source. This is a DRAFT for a human QC supervisor to review and edit before "
                "anything is saved — never invent numeric thresholds not present in the text."
            ),
            "document_filename": filename,
            "document_text": truncated_text,
            "known_vocabulary_hint": (
                "Reuse these existing catalog values when they genuinely match the document; "
                "otherwise introduce new snake_case values that describe what the document actually says."
            ),
            "known_vocabulary": known_vocabulary,
            "constraints": [
                "conditions, required_evidence and steps must be grounded in the document text.",
                "action_code and final_status should follow the document's stated disposition "
                "(e.g. FAIL/hold/rework vs PASS), not be invented.",
                "defect_types must use short snake_case tokens (e.g. scratch, dent), not free text.",
                "Write extraction_notes_vi in Vietnamese: list anything ambiguous, missing, or that "
                "the supervisor should double-check.",
                "If the document has a document number/revision/date, use it for the source fields; "
                "otherwise mark revision as 'draft' and leave effective_date null.",
            ],
        }
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You extract a draft QC policy from an uploaded document for a human "
                            "supervisor to review. Return only the requested JSON schema."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "policy_extraction",
                        "strict": False,
                        "schema": PolicyExtractionResult.model_json_schema(),
                    },
                },
            )
            content = completion.choices[0].message.content or "{}"
            result = PolicyExtractionResult.model_validate_json(content)
            self._mark_success()
            return result.model_copy(update={"provider": "groq", "model": self.model})
        except Exception as exc:
            self._mark_failure(exc)
            logger.warning("Groq policy extraction failed; upload cannot proceed: %s", exc)
            raise ReasoningUnavailableError(type(exc).__name__) from exc

    def analyze(self, state: QCState, policy: PolicyDecision) -> ReasoningAnalysis:
        prompt = {
            "task": "Analyze the inspection evidence and make the operational QC decision using only the controlled catalog and policy context.",
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
                "severity_source_id": state.get("severity_source_id"),
                "similar_defect_warning": state.get("similar_defect_warning"),
                "total_camera_views": len(state.get("camera_results") or []) or 1,
                "cross_camera_findings": state.get("finding_groups") or [],
            },
            "controlled_policy_context": policy.model_dump(mode="json"),
            "allowed_decision": {
                "action_codes": [policy.action_code],
                "final_statuses": [policy.final_status],
                "test_drive_may_be_allowed": bool(policy.test_drive_allowed),
            },
            "constraints": [
                "Never invent a measurement or acceptance threshold.",
                "Only cite source IDs included in controlled_policy_context.references.",
                "Select action_code and final_status only from allowed_decision.",
                "Never allow test drive when allowed_decision.test_drive_may_be_allowed is false.",
                "Determine severity from the selected catalog code, geometry and policy context.",
                "Explain the exact policy status and approval scope; demo approval is not production release authority.",
                "Return concise Vietnamese and English summaries.",
                "Explain the selected defect code, confidence, estimated length, location, action plan, and warnings when present.",
                "When cross_camera_findings shows the same defect_type observed on more than one "
                "camera_id, mention that in the summary as a candidate multi-view observation "
                "requiring QC confirmation (do not claim it is physically deduplicated).",
            ],
        }
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": "You are the Visual QC decision Agent. Analyze evidence, classify impact, and select an operational decision within the supplied controlled policy boundaries. Return only the requested JSON schema.",
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "visual_qc_reasoning",
                        "strict": False,
                        "schema": ReasoningAnalysis.model_json_schema(),
                    },
                },
            )
            content = completion.choices[0].message.content or "{}"
            decision_payload = ReasoningAnalysis.model_validate_json(content)
            allowed_sources = {item.id for item in policy.references}
            if not set(decision_payload.cited_source_ids).issubset(allowed_sources):
                raise ValueError("Groq returned a citation outside the approved policy context")
            if decision_payload.action_code != policy.action_code:
                raise ValueError("Groq selected an action outside the controlled policy")
            if decision_payload.final_status != policy.final_status:
                raise ValueError("Groq selected a final status outside the controlled policy")
            if decision_payload.allow_test_drive and not policy.test_drive_allowed:
                raise ValueError("Groq attempted to allow a blocked test drive")
            self._mark_success()
            # Guarantee the severity threshold's own source is cited even if the LLM didn't
            # pick it up from the prompt — mirrors DeterministicReasoningService.analyze().
            cited_source_ids = list(decision_payload.cited_source_ids)
            severity_source_id = state.get("severity_source_id")
            if severity_source_id and severity_source_id not in cited_source_ids:
                cited_source_ids.append(severity_source_id)
            return decision_payload.model_copy(
                update={
                    "provider": "groq",
                    "model": self.model,
                    "cited_source_ids": cited_source_ids,
                }
            )
        except Exception as exc:
            self._mark_failure(exc)
            logger.warning("Groq decision failed; HITL is required: %s", exc)
            raise ReasoningUnavailableError(type(exc).__name__) from exc
