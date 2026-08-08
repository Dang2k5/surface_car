from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from backend.app.schemas import (
    ClassificationResponse,
    DecisionRecommendation,
    DecisionResponse,
    DefectResponse,
    WorkflowRunResponse,
    WorkflowStatus,
    WorkflowStep,
)


class MockQCAgent:
    """Deterministic policy orchestration, intentionally independent of LangGraph."""

    def _stopped(
        self,
        inspection_id: str,
        detections: list[DefectResponse],
        classifications: list[ClassificationResponse],
        steps: list[WorkflowStep],
        step_name: str,
        detail: str | None = None,
        error_code: str | None = None,
    ) -> WorkflowRunResponse:
        steps.append(
            WorkflowStep(
                name=step_name,
                status="STOPPED",
                detail=detail or f"Injected demo failure at {step_name}; downstream stages were not executed.",
                policy_refs=["DEMO-QC-RECOVERY-001"],
                error_code=error_code or f"SIMULATED_{step_name.upper()}_FAILURE",
                retryable=True,
            )
        )
        return WorkflowRunResponse(
            id=str(uuid4()),
            inspection_id=inspection_id,
            status=WorkflowStatus.STOPPED_RETRY_REQUIRED,
            steps=steps,
            detections=detections,
            classifications=classifications,
            decision=None,
            hitl_required=False,
            created_at=datetime.now(UTC),
        )

    def run(
        self,
        inspection_id: str,
        detections: list[DefectResponse],
        classify: Callable[[], list[ClassificationResponse]],
        decide: Callable[[], DecisionResponse],
        fail_at_step: str | None = None,
    ) -> WorkflowRunResponse:
        steps: list[WorkflowStep] = []
        classifications: list[ClassificationResponse] = []

        if fail_at_step == "detect":
            return self._stopped(inspection_id, detections, classifications, steps, "detect")
        steps.append(
            WorkflowStep(
                name="detect",
                status="COMPLETED",
                detail=f"Accepted {len(detections)} persisted mock CV detection(s).",
                policy_refs=["DEMO-QC-DATA-001"],
            )
        )

        if fail_at_step == "validate":
            return self._stopped(inspection_id, detections, classifications, steps, "validate")
        invalid_detections = [item for item in detections if item.bbox is None or not 0 <= item.confidence <= 1]
        if invalid_detections:
            return self._stopped(
                inspection_id,
                detections,
                classifications,
                steps,
                "validate",
                detail=f"Rejected {len(invalid_detections)} incomplete CV detection(s); downstream stages were not executed.",
                error_code="CV_PAYLOAD_VALIDATION_FAILED",
            )
        steps.append(
            WorkflowStep(
                name="validate",
                status="COMPLETED",
                detail="Validated CV payload completeness, bbox, confidence, and inspection linkage.",
                policy_refs=["DEMO-QC-DATA-001"],
            )
        )

        if fail_at_step == "classify":
            return self._stopped(inspection_id, detections, classifications, steps, "classify")
        classifications = classify()
        steps.append(
            WorkflowStep(
                name="classify",
                status="COMPLETED",
                detail=f"Resolved {len(classifications)} domain classification(s) from the mock rule catalog.",
                policy_refs=["DEMO-QC-CLASSIFY-001"],
            )
        )

        if fail_at_step == "policy_evaluate":
            return self._stopped(inspection_id, detections, classifications, steps, "policy_evaluate")
        decision = decide()
        steps.append(
            WorkflowStep(
                name="policy_evaluate",
                status="COMPLETED",
                detail=f"Matched action {decision.action_code} from {len(decision.policy_refs)} demo policy reference(s).",
                policy_refs=decision.policy_refs,
            )
        )
        steps.append(
            WorkflowStep(
                name="route",
                status="COMPLETED",
                detail=f"Prepared controlled route: {decision.route}. Test drive allowed: {decision.test_drive_allowed}.",
                policy_refs=decision.policy_refs,
            )
        )

        hitl_required = decision.recommendation in {
            DecisionRecommendation.MANUAL_VISUAL_REINSPECTION,
            DecisionRecommendation.HITL_REQUIRED,
        }
        steps.append(
            WorkflowStep(
                name="hitl",
                status="WAITING" if hitl_required else "NOT_REQUIRED",
                detail="A named QC reviewer must complete the inspection." if hitl_required else "No manual checkpoint is required by the matched demo policy.",
                policy_refs=["DEMO-QC-HITL-001"] if hitl_required else decision.policy_refs,
            )
        )
        return WorkflowRunResponse(
            id=str(uuid4()),
            inspection_id=inspection_id,
            status=WorkflowStatus.WAITING_FOR_HITL if hitl_required else WorkflowStatus.COMPLETED,
            steps=steps,
            detections=detections,
            classifications=classifications,
            decision=decision,
            hitl_required=hitl_required,
            created_at=datetime.now(UTC),
        )
