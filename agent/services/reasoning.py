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
        if recommendation_code == "SURFACE_DAMAGE_ASSESSMENT_AND_REINSPECT":
            return (
                f"The model detected {defect} at {confidence:.0%} confidence. "
                "Pilot policy requires controlled surface assessment and QC reinspection "
                "before any release or repair method is selected."
            )
        if recommendation_code == "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT":
            return (
                f"The {defect} is confirmed at {confidence:.0%} confidence. Vehicle "
                "release remains blocked until Body Repair evaluates panel geometry "
                "and repairability."
            )
        if recommendation_code in {
            "ISOLATE_FOR_GLASS_REPAIR",
            "ISOLATE_FOR_LIGHTING_REPAIR",
            "IMMOBILIZE_FOR_TIRE_SERVICE",
        }:
            return (
                f"The model detected {defect} at {confidence:.0%} confidence. "
                "Vehicle movement and release remain blocked pending specialist assessment."
            )
        return "The final action was selected by an authorized QC reviewer."
