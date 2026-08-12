from __future__ import annotations

import json
import logging
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


class ReasoningService(Protocol):
    def analyze(self, state: QCState, policy: PolicyDecision) -> ReasoningAnalysis: ...


class DeterministicReasoningService:
    """Auditable fallback that never invents measurements or acceptance limits."""

    def analyze(self, state: QCState, policy: PolicyDecision) -> ReasoningAnalysis:
        defect = state.get("defect_type", "unknown")
        confidence = float(state.get("confidence", 0.0))
        missing = policy.missing_evidence
        missing_text = ", ".join(missing) if missing else "none"
        scope_note_en = (
            "The policy is approved for production use."
            if policy.approval_scope == "PRODUCTION"
            else "The policy is approved for demo workflow validation only, not production release."
        )
        scope_note_vi = (
            "Policy đã được phê duyệt cho sản xuất."
            if policy.approval_scope == "PRODUCTION"
            else "Policy đã được phê duyệt cho demo workflow, không phải quyền release sản xuất."
        )
        summary_en = (
            f"The model detected {defect} at {confidence:.0%} confidence. "
            f"Policy {policy.policy_id} selected '{policy.action_label}'; missing evidence: {missing_text}. "
            f"{scope_note_en}"
        )
        summary_vi = (
            f"Model phát hiện {defect} với confidence {confidence:.0%}. "
            f"Policy {policy.policy_id} chọn '{policy.action_label}'; evidence còn thiếu: {missing_text}. "
            f"{scope_note_vi}"
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

    def analyze(self, state: QCState, policy: PolicyDecision) -> ReasoningAnalysis:
        prompt = {
            "task": "Explain the policy outcome and identify missing evidence. Do not change the action code, final status, release permission, measurements, or citations.",
            "inspection": {
                "defect_type": state.get("defect_type"),
                "confidence": state.get("confidence"),
                "panel": state.get("panel"),
                "severity": state.get("severity"),
                "verify_result": state.get("verify_result"),
            },
            "authoritative_policy_result": policy.model_dump(mode="json"),
            "constraints": [
                "Never invent a measurement or acceptance threshold.",
                "Only cite source IDs included in authoritative_policy_result.references.",
                "Explain the exact policy status and approval scope; demo approval is not production release authority.",
                "Return concise Vietnamese and English summaries.",
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
            return ReasoningAnalysis(
                **payload.model_dump(),
                provider="groq",
                model=self.model,
            )
        except Exception as exc:  # fail closed to deterministic explanation
            logger.warning("Groq reasoning unavailable; using deterministic fallback: %s", exc)
            result = self.fallback.analyze(state, policy)
            return result.model_copy(update={"fallback_reason": type(exc).__name__})
