from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from agent.graph.state import QCState, TraceEvent
from agent.services.detector import DetectorService
from agent.services.reasoning import ReasoningService
from agent.services.repository import QCRepository
from agent.services.verifier import VerifierService


def _trace(node: str, detail: str, status: str = "COMPLETED") -> list[TraceEvent]:
    return [{"node": node, "status": status, "detail": detail}]


class QCNodes:
    def __init__(
        self,
        detector: DetectorService,
        verifier: VerifierService,
        reasoning: ReasoningService,
        repository: QCRepository,
    ) -> None:
        self.detector = detector
        self.verifier = verifier
        self.reasoning = reasoning
        self.repository = repository

    def prepare_input(self, state: QCState) -> dict[str, Any]:
        image_paths = state.get("image_paths", [])
        image_url = state.get("image_url", "")
        if not image_url and not image_paths:
            raise ValueError("image_url or image_paths is required")
        return {
            "verify_count": 0,
            "verify_result": "NOT_RUN",
            "human_required": False,
            "human_decision": None,
            "retry_count": state.get("retry_count", 0),
            "max_retries": state.get("max_retries", 2),
            "error": None,
            "execution_trace": _trace("prepare_input", "Input and image evidence validated."),
        }

    def detect_defect(self, state: QCState) -> dict[str, Any]:
        detection = self.detector.detect(state)
        detected = bool(detection.get("defect_detected"))
        return {
            **detection,
            "execution_trace": _trace(
                "detect_defect",
                f"Mock detector returned defect_detected={detected}, "
                f"confidence={float(detection.get('confidence', 0.0)):.2f}.",
            ),
        }

    def assess_result(self, state: QCState) -> dict[str, Any]:
        if not state.get("defect_detected", False):
            route = "PASS"
            decision = "PASS"
            reason = "No body-panel defect was detected."
        elif state.get("verify_result") == "CONFIRMED":
            route = "CONFIRMED"
            decision = "DEFECT_CONFIRMED"
            reason = "Second-pass verification confirmed the defect."
        elif state.get("verify_result") == "UNCERTAIN" and state.get("verify_count", 0) >= 2:
            route = "HITL"
            decision = "HUMAN_REVIEW_REQUIRED"
            reason = "Verification remained uncertain after the maximum two passes."
        elif state.get("confidence", 0.0) >= 0.85:
            route = "CONFIRMED"
            decision = "DEFECT_CONFIRMED"
            reason = "Detector confidence meets the automatic-confirmation threshold."
        elif state.get("confidence", 0.0) >= 0.50:
            route = "VERIFY"
            decision = "VERIFY_REQUIRED"
            reason = "The result is ambiguous and requires a second-pass verification."
        else:
            route = "HITL"
            decision = "HUMAN_REVIEW_REQUIRED"
            reason = "Confidence is below the safe automation threshold."
        return {
            "assessment_route": route,
            "decision": decision,
            "reason": reason,
            "human_required": route == "HITL",
            "execution_trace": _trace("assess_result", f"Route={route}. {reason}"),
        }

    def verify_defect(self, state: QCState) -> dict[str, Any]:
        result = self.verifier.verify(state)
        return {
            **result,
            "execution_trace": _trace(
                "verify_defect",
                f"Verification pass {result['verify_count']} returned {result['verify_result']}.",
            ),
        }

    def human_review(self, state: QCState) -> dict[str, Any]:
        response = interrupt(
            {
                "type": "visual_qc_review",
                "inspection_id": state["inspection_id"],
                "vehicle_id": state["vehicle_id"],
                "defect_type": state.get("defect_type"),
                "confidence": state.get("confidence"),
                "verify_count": state.get("verify_count", 0),
                "reason": state.get("reason"),
                "allowed_actions": ["APPROVE", "REJECT", "OVERRIDE"],
            }
        )
        if not isinstance(response, dict):
            raise ValueError("HITL resume payload must be an object")
        action = str(response.get("action", "")).upper()
        if action not in {"APPROVE", "REJECT", "OVERRIDE"}:
            raise ValueError("HITL action must be APPROVE, REJECT, or OVERRIDE")
        decision = "DEFECT_CONFIRMED" if action in {"APPROVE", "OVERRIDE"} else "REINSPECTION_REQUIRED"
        return {
            "human_required": False,
            "human_decision": response,
            "decision": decision,
            "reason": str(response.get("reason") or f"Human reviewer selected {action}."),
            "execution_trace": _trace("human_review", f"HITL resumed with action={action}."),
        }

    def generate_recommendation(self, state: QCState) -> dict[str, Any]:
        human_action = str((state.get("human_decision") or {}).get("action", "")).upper()
        override = (state.get("human_decision") or {}).get("recommendation")
        if human_action == "REJECT":
            recommendation_code = "MANUAL_VISUAL_REINSPECTION"
            final_status = "HOLD_FOR_QC"
        elif human_action == "OVERRIDE" and override:
            recommendation_code = str(override)
            final_status = "HUMAN_OVERRIDE_APPLIED"
        elif state.get("defect_type") == "scratch" and state.get("severity") in {"C", "D"}:
            recommendation_code = "SURFACE_POLISH_AND_REINSPECT"
            final_status = "CONTROLLED_REPAIR"
        else:
            recommendation_code = "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT"
            final_status = "HOLD_FOR_REWORK"
        recommendation_labels = {
            "MANUAL_VISUAL_REINSPECTION": "Keep the vehicle on hold and perform a new manual visual inspection",
            "SURFACE_POLISH_AND_REINSPECT": "Polish the affected surface and perform a documented reinspection",
            "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT": "Hold the vehicle and transfer it to Body Repair for technical assessment",
        }
        recommendation = recommendation_labels.get(
            recommendation_code,
            recommendation_code.replace("_", " ").strip().title(),
        )
        reason = self.reasoning.explain(state, recommendation_code)
        return {
            "recommendation_code": recommendation_code,
            "recommendation": recommendation,
            "final_status": final_status,
            "reason": reason,
            "execution_trace": _trace(
                "generate_recommendation",
                f"Selected action code {recommendation_code} using deterministic QC rules.",
            ),
        }

    def save_result(self, state: QCState) -> dict[str, Any]:
        update: dict[str, Any] = {}
        if state.get("decision") == "PASS":
            update = {
                "recommendation_code": "RELEASE_TO_NEXT_QUALITY_GATE",
                "recommendation": "Release the vehicle to the next quality gate",
                "final_status": "PASS",
                "reason": state.get("reason", "No defect detected."),
            }
        completed_state: QCState = {
            **state,
            **update,
            "execution_trace": [
                *state.get("execution_trace", []),
                *_trace("save_result", "Final state persisted through the repository adapter."),
            ],
        }
        self.repository.save(completed_state)
        return {
            **update,
            "execution_trace": _trace(
                "save_result",
                "Final state persisted through the repository adapter.",
            ),
        }
