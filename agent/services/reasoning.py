from __future__ import annotations

from typing import Protocol

from agent.graph.state import QCState


class ReasoningService(Protocol):
    def explain(self, state: QCState, recommendation_code: str) -> str: ...


class DeterministicReasoningService:
    """Deterministic formatter for auditable QC decision reasons."""

    def explain(self, state: QCState, recommendation_code: str) -> str:
        defect = state.get("defect_type", "unknown")
        confidence = state.get("confidence", 0.0)
        human_action = str((state.get("human_decision") or {}).get("action", "")).upper()
        if human_action == "REJECT":
            return (
                "The reviewer did not confirm the automated finding. The vehicle "
                "remains held for a fresh manual visual inspection."
            )
        if recommendation_code == "SURFACE_POLISH_AND_REINSPECT":
            return (
                f"The {defect} is confirmed at {confidence:.0%} confidence and is "
                "limited to a cosmetic severity class. Controlled polishing must "
                "be followed by a documented visual reinspection."
            )
        if recommendation_code == "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT":
            return (
                f"The {defect} is confirmed at {confidence:.0%} confidence. Vehicle "
                "release remains blocked until Body Repair evaluates panel geometry "
                "and repairability."
            )
        return "The final action was selected by an authorized QC reviewer."
