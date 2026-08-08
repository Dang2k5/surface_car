from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .schemas import DecisionRecommendation


@dataclass(frozen=True)
class PolicyDecision:
    recommendation: DecisionRecommendation
    action_code: str
    action: str
    route: str
    reason_codes: list[str]
    policy_refs: list[str]
    method_steps: list[str]
    explanation: str
    test_drive_allowed: bool


def evaluate_demo_qc_policy(classifications: Iterable[Any], defect_count: int) -> PolicyDecision:
    """Evaluate the versioned baseline demo policy.

    References beginning with DEMO-QC are internal simulation policies. They
    must be replaced by plant-approved specifications and work instructions
    before production use.
    """
    items = list(classifications)
    if not items:
        if defect_count:
            return PolicyDecision(
                recommendation=DecisionRecommendation.RETRY_REQUIRED,
                action_code="RETRY_CLASSIFICATION_PIPELINE",
                action="Stop routing and retry classification",
                route="FNS Data Recovery Queue",
                reason_codes=["CLASSIFICATION_MISSING"],
                policy_refs=["DEMO-QC-DATA-001"],
                method_steps=[
                    "Keep the vehicle at the FNS quality gate.",
                    "Verify detector payload and required master data.",
                    "Retry classification from the failed checkpoint.",
                    "Escalate to QC if the retry fails again.",
                ],
                explanation="A detected defect has no classification result; downstream policy evaluation is prohibited.",
                test_drive_allowed=False,
            )
        return PolicyDecision(
            recommendation=DecisionRecommendation.PASS,
            action_code="RELEASE_TO_NEXT_QUALITY_GATE",
            action="Release to the next approved quality gate",
            route="Final Line Release Gate",
            reason_codes=["NO_DEFECTS"],
            policy_refs=["DEMO-QC-RELEASE-001"],
            method_steps=[
                "Record the no-defect inspection result.",
                "Verify VIN and required completion checks.",
                "Release the vehicle to the next quality gate.",
            ],
            explanation="No defect was detected by the mock CV payload.",
            test_drive_allowed=True,
        )

    reasons: list[str] = []
    for item in items:
        if item["classification_confidence"] < 0.80:
            reasons.append("LOW_CLASSIFICATION_CONFIDENCE")
        if item["measurement_mm"] > item["tolerance_mm"]:
            reasons.append("MEASUREMENT_OVER_TOLERANCE")
        if item["severity_rank"] in {"P", "S", "A"}:
            reasons.append("HIGH_SEVERITY_RANK")
        if item["material"] == "hot_stamped_steel":
            reasons.append("HOT_STAMPED_STEEL")
    reasons = list(dict.fromkeys(reasons))

    if "LOW_CLASSIFICATION_CONFIDENCE" in reasons:
        return PolicyDecision(
            recommendation=DecisionRecommendation.MANUAL_VISUAL_REINSPECTION,
            action_code="MANUAL_VISUAL_REINSPECTION",
            action="Perform manual visual reinspection and measurement confirmation",
            route="FNS QC Review Bay",
            reason_codes=reasons,
            policy_refs=["DEMO-QC-HITL-001", "DEMO-QC-DATA-001"],
            method_steps=[
                "Hold the vehicle at the QC review bay.",
                "Repeat visual inspection under controlled lighting.",
                "Confirm panel, material, location, and measurement.",
                "Record a named QC decision before any release.",
            ],
            explanation="Confidence is below the demo-policy threshold, so automated routing is blocked.",
            test_drive_allowed=False,
        )

    first = items[0]
    if first["panel"] == "hood_class_a_surface":
        return PolicyDecision(
            recommendation=DecisionRecommendation.PAINT_REPAIR_ASSESSMENT,
            action_code="ISOLATE_FOR_PAINT_REPAIR_ASSESSMENT",
            action="HOLD for paint repair assessment and controlled reinspection",
            route="Paint Rework Assessment",
            reason_codes=reasons or ["CLASS_A_SURFACE_DEFECT"],
            policy_refs=["DEMO-QC-PAINT-001", "DEMO-QC-HOLD-001"],
            method_steps=[
                "Apply HOLD status and block test drive.",
                "Protect the affected surface from contamination.",
                "Route to paint repair assessment under an approved work instruction.",
                "Reinspect appearance and measurement before release.",
            ],
            explanation="The paint/class-A surface condition requires controlled paint-repair assessment in this demo policy.",
            test_drive_allowed=False,
        )

    if reasons:
        return PolicyDecision(
            recommendation=DecisionRecommendation.BODY_REPAIR_ASSESSMENT,
            action_code="ISOLATE_FOR_BODY_REPAIR_ASSESSMENT",
            action="HOLD for body repair engineering assessment",
            route="Body Rework Assessment",
            reason_codes=reasons,
            policy_refs=["DEMO-QC-BODY-001", "DEMO-QC-HOLD-001"],
            method_steps=[
                "Apply HOLD status and block test drive.",
                "Do not perform unapproved local forming or cold work.",
                "Confirm material and repairability against the approved repair manual.",
                "Route to body repair assessment and reinspect after repair.",
            ],
            explanation="One or more demo-policy safety gates were triggered; local cosmetic repair is not authorized.",
            test_drive_allowed=False,
        )

    return PolicyDecision(
        recommendation=DecisionRecommendation.SURFACE_POLISH_REINSPECT,
        action_code="SURFACE_POLISH_AND_REINSPECT",
        action="Perform approved surface polish, then visual reinspection",
        route="Cosmetic Repair Station",
        reason_codes=["MINOR_DEFECT_WITHIN_TOLERANCE"],
        policy_refs=["DEMO-QC-COSMETIC-001", "DEMO-QC-RELEASE-001"],
        method_steps=[
            "Protect adjacent trim and clean the affected surface.",
            "Apply the approved surface-polish work instruction.",
            "Repeat visual inspection under controlled lighting.",
            "Release only after QC confirms the result.",
        ],
        explanation="The defect is within the demo tolerance and may enter controlled cosmetic repair and reinspection.",
        test_drive_allowed=True,
    )
