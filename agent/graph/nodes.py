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
        try:
            detection = self.detector.detect(state)
        except Exception as error:
            return {
                "defect_detected": False,
                "defect_type": "unknown",
                "confidence": 0.0,
                "bbox": None,
                "segmentation_result": None,
                "detections": [],
                "inference_status": "ERROR",
                "error": str(error),
                "execution_trace": _trace(
                    "detect_defect",
                    f"Model inference failed safely: {error}",
                    "FAILED",
                ),
            }
        detected = bool(detection.get("defect_detected"))
        model_name = str(detection.get("model_name") or type(self.detector).__name__)
        return {
            **detection,
            "execution_trace": _trace(
                "detect_defect",
                f"{model_name} returned defect_detected={detected}, "
                f"confidence={float(detection.get('confidence', 0.0)):.2f}, "
                f"detections={len(detection.get('detections', []))}.",
            ),
        }

    def assess_result(self, state: QCState) -> dict[str, Any]:
        confidence = float(state.get("confidence", 0.0))
        confirmed_threshold = float(state.get("confirmed_threshold", 0.85))
        verify_threshold = float(state.get("verify_threshold", 0.50))
        if state.get("inference_status") == "ERROR":
            route = "HITL"
            decision = "MODEL_ERROR_REVIEW_REQUIRED"
            reason = "Model inference failed; fail-safe QC review is required."
        elif not state.get("defect_detected", False) and not state.get("auto_pass_enabled", True):
            route = "HITL"
            decision = "NO_DETECTION_REVIEW_REQUIRED"
            reason = "Pilot mode blocks automatic PASS when the model returns no detection."
        elif not state.get("defect_detected", False):
            route = "PASS"
            decision = "PASS"
            reason = "No body-panel defect was detected."
        elif state.get("defect_type") == "unknown":
            route = "HITL"
            decision = "UNKNOWN_CLASS_REVIEW_REQUIRED"
            reason = "The model returned a class that is not mapped to the QC taxonomy."
        elif state.get("verify_result") == "CONFIRMED":
            route = "CONFIRMED"
            decision = "DEFECT_CONFIRMED"
            reason = "Second-pass verification confirmed the defect."
        elif state.get("verify_result") == "UNCERTAIN" and state.get("verify_count", 0) >= 2:
            route = "HITL"
            decision = "HUMAN_REVIEW_REQUIRED"
            reason = "Verification remained uncertain after the maximum two passes."
        elif confidence >= confirmed_threshold:
            route = "CONFIRMED"
            decision = "DEFECT_CONFIRMED"
            reason = "Detector confidence meets the automatic-confirmation threshold."
        elif confidence >= verify_threshold:
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
        elif state.get("defect_type") == "scratch":
            recommendation_code = "SURFACE_DAMAGE_ASSESSMENT_AND_REINSPECT"
            final_status = "HOLD_FOR_QC"
        elif state.get("defect_type") == "glass_shatter":
            recommendation_code = "ISOLATE_FOR_GLASS_REPAIR"
            final_status = "HOLD_FOR_REWORK"
        elif state.get("defect_type") == "lamp_broken":
            recommendation_code = "ISOLATE_FOR_LIGHTING_REPAIR"
            final_status = "HOLD_FOR_REWORK"
        elif state.get("defect_type") == "tire_flat":
            recommendation_code = "IMMOBILIZE_FOR_TIRE_SERVICE"
            final_status = "HOLD_FOR_REWORK"
        else:
            recommendation_code = "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT"
            final_status = "HOLD_FOR_REWORK"
        recommendation_labels = {
            "MANUAL_VISUAL_REINSPECTION": "Keep the vehicle on hold and perform a new manual visual inspection",
            "SURFACE_POLISH_AND_REINSPECT": "Polish the affected surface and perform a documented reinspection",
            "SURFACE_DAMAGE_ASSESSMENT_AND_REINSPECT": "Hold for controlled surface assessment and documented reinspection",
            "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT": "Hold the vehicle and transfer it to Body Repair for technical assessment",
            "ISOLATE_FOR_GLASS_REPAIR": "Hold the vehicle and transfer it for glass damage assessment",
            "ISOLATE_FOR_LIGHTING_REPAIR": "Hold the vehicle and transfer it for lighting system repair",
            "IMMOBILIZE_FOR_TIRE_SERVICE": "Immobilize the vehicle and transfer it for tire service",
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
