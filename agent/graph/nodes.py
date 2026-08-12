from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from agent.graph.state import QCState, TraceEvent
from agent.services.detector import DetectorService
from agent.services.policy import PolicyCatalog
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
        policy_catalog: PolicyCatalog,
        repository: QCRepository,
    ) -> None:
        self.detector = detector
        self.verifier = verifier
        self.reasoning = reasoning
        self.policy_catalog = policy_catalog
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
        policy = self.policy_catalog.evaluate(state)
        review = policy.document_review
        return {
            "assessment_route": route,
            "decision": decision,
            "reason": reason,
            "human_required": route == "HITL",
            "policy_decision": policy.model_dump(mode="json"),
            "execution_trace": _trace(
                "assess_result",
                f"Route={route}. Policy lookup matched {review.matched_document_count} controlled "
                f"document(s), found {len(review.missing_data)} missing evidence item(s), and "
                f"raised {len(review.warnings)} document-control warning(s).",
            ),
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
        policy = self.policy_catalog.evaluate(state)
        human_action = str((state.get("human_decision") or {}).get("action", "")).upper()
        override = (state.get("human_decision") or {}).get("recommendation")
        if human_action == "OVERRIDE" and override:
            policy = policy.model_copy(
                update={
                    "action_code": str(override),
                    "action_label": str(override).replace("_", " ").strip().title(),
                    "final_status": "HUMAN_OVERRIDE_APPLIED",
                    "production_eligible": False,
                }
            )
        analysis = self.reasoning.analyze(state, policy)
        return {
            "recommendation_code": policy.action_code,
            "recommendation": policy.action_label,
            "final_status": policy.final_status,
            "reason": analysis.summary_en,
            "human_required": policy.human_required,
            "policy_decision": policy.model_dump(mode="json"),
            "ai_analysis": analysis.model_dump(mode="json"),
            "execution_trace": _trace(
                "generate_recommendation",
                f"Policy {policy.policy_id}@{policy.policy_revision} selected "
                f"{policy.action_code}; reasoning={analysis.provider}.",
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
