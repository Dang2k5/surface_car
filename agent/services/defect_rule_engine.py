"""Deterministic defect-code selection -- the "decide" step in detect -> classify -> decide
-> HITL (docs/DE_BAI_GOC.md) must run on a confidence/measurement THRESHOLD, not an LLM: the
catalog's `classification_rule` values are pure numeric thresholds/counts, so asking an LLM
to "decide" among them added latency, an outage dependency and hallucination risk without
adding any actual decision-making value.

This engine only ever picks a code when a structured rule (`rule_type`/`min_mm`/`max_mm`/
`min_detection_count` on the defect_catalog row, see backend/app/database.py) unambiguously
matches. Anything it cannot confidently decide -- no candidates, ambiguous, unstructured
data, or a code explicitly marked `REQUIRES_HUMAN` -- returns None, and the caller
(agent/graph/nodes.py's QCNodes._classify_local_detection) routes that finding to HITL. This
engine never guesses: a wrong "confident" answer here would be a wrong QC decision, so
"I don't know" must always be a real, cheap, always-available outcome.
"""
from __future__ import annotations

from typing import Any

from agent.services.reasoning import DefectCodeClassification


def classify_by_rule(
    overlay: dict[str, Any], candidates: list[dict[str, Any]]
) -> DefectCodeClassification | None:
    """Select one defect_code from `candidates` using each candidate's own structured rule.

    `overlay` is the same per-detection state QCNodes._classify_local_detection already
    builds for the (removed) LLM call: it carries `visual_measurements` (from YOLO,
    agent/services/yolo_detector.py) and `detections` (every raw detection in this
    inspection, across all cameras, via the just-computed `base_detection` merge) alongside
    the usual QCState fields.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        only = candidates[0]
        # REQUIRES_HUMAN is an explicit "a human must confirm this, always" marker on the
        # code itself -- being the only candidate doesn't remove that requirement, unlike an
        # unconfigured (`rule_type` is None) code, where "only one option" really does mean
        # there was nothing to disambiguate in the first place.
        if only.get("rule_type") == "REQUIRES_HUMAN":
            return None
        return _matched(only, candidates, "Chỉ có 1 mã lỗi phù hợp trong danh mục cho loại lỗi này.")

    # MIN_COUNT is checked first, ahead of THRESHOLD_MM: a cluster of same-type findings
    # (e.g. "at least 2 dent detections") is a categorically different, worse condition than
    # any single finding's own size band, and must win over a width-band match rather than
    # be treated as merely "ambiguous with it".
    #
    # "Cluster" means physically localized: same defect_type AND same camera (i.e. the same
    # general body area), not just anywhere on the vehicle -- a scratch on the front bumper
    # and an unrelated one on the tailgate must not count as a 2-vết cluster.
    defect_type = str(overlay.get("defect_type") or "")
    camera_id = overlay.get("camera_id")
    sibling_count = sum(
        1
        for item in (overlay.get("detections") or [])
        if item.get("class_name") == defect_type and item.get("camera_id") == camera_id
    )
    count_matches = [
        item
        for item in candidates
        if item.get("rule_type") == "MIN_COUNT"
        and item.get("min_detection_count") is not None
        and sibling_count >= int(item["min_detection_count"])
    ]
    if len(count_matches) == 1:
        item = count_matches[0]
        return _matched(
            item,
            candidates,
            f"Phát hiện {sibling_count} vùng lỗi cùng loại — khớp điều kiện tối thiểu "
            f"{item['min_detection_count']} của mã {item['defect_code']}.",
        )
    if len(count_matches) > 1:
        return None  # catalog misconfiguration (overlapping MIN_COUNT rules) -> HITL, not a guess

    visual = overlay.get("visual_measurements") or {}
    width_mm = visual.get("estimated_width_mm")
    if width_mm is None:
        return None
    width = float(width_mm)
    threshold_matches = []
    for item in candidates:
        if item.get("rule_type") != "THRESHOLD_MM":
            continue
        min_mm = item.get("min_mm")
        max_mm = item.get("max_mm")
        lower_ok = min_mm is None or width > float(min_mm)
        upper_ok = max_mm is None or width <= float(max_mm)
        if lower_ok and upper_ok:
            threshold_matches.append(item)

    if len(threshold_matches) != 1:
        # 0 matches: no configured band covers this width (gap in the catalog).
        # >=2 matches: overlapping bands. Either way this is not a confident decision.
        return None

    item = threshold_matches[0]
    return _matched(
        item, candidates, f"Bề rộng ước lượng {width:.1f}mm khớp ngưỡng mã {item['defect_code']}."
    )


def _matched(
    item: dict[str, Any], candidates: list[dict[str, Any]], reason: str
) -> DefectCodeClassification:
    return DefectCodeClassification(
        defect_code=str(item["defect_code"]),
        defect_family=item.get("defect_family"),
        confidence=1.0,
        rationale_vi=reason,
        candidate_codes=[str(c.get("defect_code")) for c in candidates],
        similar_observation_warning=False,
        provider="rule_engine",
        model="threshold-v1",
    )


__all__ = ("classify_by_rule",)
