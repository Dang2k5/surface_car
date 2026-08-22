from __future__ import annotations

from typing import Literal

from agent.graph.state import QCState

AssessmentRoute = Literal["PASS", "CONFIRMED", "VERIFY", "HITL"]
HumanReviewRoute = Literal["ESCALATE_TO_SUPERVISOR", "CONTINUE"]


def route_assessment(state: QCState) -> AssessmentRoute:
    """Conditional edge selector after assess_result."""
    return state.get("assessment_route", "HITL")


def route_after_human_review(state: QCState) -> HumanReviewRoute:
    """An operator's OVERRIDE (chuyển cấp xét duyệt) always needs a second, supervisor-only
    sign-off before the graph is allowed to finalize a decision — APPROVE/REJECT resolve here."""
    action = str((state.get("human_decision") or {}).get("action", "")).upper()
    return "ESCALATE_TO_SUPERVISOR" if action == "OVERRIDE" else "CONTINUE"
