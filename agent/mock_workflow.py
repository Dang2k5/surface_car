from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
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
    """Deterministic mock orchestration, intentionally independent of LangGraph."""

    def run(
        self,
        inspection_id: str,
        detections: list[DefectResponse],
        classify: Callable[[], list[ClassificationResponse]],
        decide: Callable[[], DecisionResponse],
    ) -> WorkflowRunResponse:
        classifications = classify()
        decision = decide()
        hitl_required = decision.recommendation == DecisionRecommendation.HITL_REQUIRED
        steps = [
            WorkflowStep(
                name="detect",
                status="COMPLETED",
                detail=f"Loaded {len(detections)} persisted mock YOLO detection(s).",
            ),
            WorkflowStep(
                name="classify",
                status="COMPLETED",
                detail=f"Created {len(classifications)} mock classification(s).",
            ),
            WorkflowStep(
                name="decide",
                status="COMPLETED",
                detail=f"Recommendation: {decision.recommendation.value}.",
            ),
            WorkflowStep(
                name="hitl",
                status="WAITING" if hitl_required else "NOT_REQUIRED",
                detail="QC review is required before execution." if hitl_required else "No human review required by mock rules.",
            ),
        ]
        return WorkflowRunResponse(
            id=str(uuid4()),
            inspection_id=inspection_id,
            status=WorkflowStatus.WAITING_FOR_HITL if hitl_required else WorkflowStatus.COMPLETED,
            steps=steps,
            detections=detections,
            classifications=classifications,
            decision=decision,
            hitl_required=hitl_required,
            created_at=datetime.now(timezone.utc),
        )
