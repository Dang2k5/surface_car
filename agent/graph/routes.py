from __future__ import annotations

from typing import Literal

from agent.graph.state import QCState

AssessmentRoute = Literal["PASS", "CONFIRMED", "VERIFY", "HITL"]


def route_assessment(state: QCState) -> AssessmentRoute:
    """Conditional edge selector after assess_result."""
    return state.get("assessment_route", "HITL")
