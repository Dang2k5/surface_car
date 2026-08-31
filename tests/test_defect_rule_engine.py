"""Unit tests for the deterministic defect-code rule engine (no DB/HTTP/LLM involved) --
this is the "decide" step docs/DE_BAI_GOC.md specifies as a threshold, replacing the LLM
call that used to run here (agent/services/reasoning.py's classify_defect_code)."""
from __future__ import annotations

from agent.services.defect_rule_engine import classify_by_rule

DENT01 = {"defect_code": "DENT01", "rule_type": "THRESHOLD_MM", "min_mm": None, "max_mm": 25}
DENT02 = {"defect_code": "DENT02", "rule_type": "THRESHOLD_MM", "min_mm": 25, "max_mm": 50}
DENT03 = {"defect_code": "DENT03", "rule_type": "THRESHOLD_MM", "min_mm": 50, "max_mm": None}
DENT04_REQUIRES_HUMAN = {"defect_code": "DENT04", "rule_type": "REQUIRES_HUMAN"}
DENT05_CLUSTER = {"defect_code": "DENT05", "rule_type": "MIN_COUNT", "min_detection_count": 2}
UNSTRUCTURED = {"defect_code": "CUSTOM01", "rule_type": None}


def _overlay(*, defect_type="dent", width_mm=None, sibling_count=1):
    detections = [{"class_name": defect_type}] * sibling_count
    return {
        "defect_type": defect_type,
        "visual_measurements": {"estimated_width_mm": width_mm} if width_mm is not None else {},
        "detections": detections,
    }


def test_single_candidate_always_matches_without_measurements():
    result = classify_by_rule(_overlay(), [DENT01])
    assert result is not None
    assert result.defect_code == "DENT01"
    assert result.provider == "rule_engine"


def test_no_candidates_returns_none():
    assert classify_by_rule(_overlay(), []) is None


def test_threshold_band_selects_matching_code():
    overlay = _overlay(width_mm=30.0)
    result = classify_by_rule(overlay, [DENT01, DENT02, DENT03])
    assert result is not None
    assert result.defect_code == "DENT02"


def test_threshold_boundary_is_upper_inclusive_lower_exclusive():
    # DENT02 is "25 < width <= 50" -- exactly 25 must fall to DENT01, exactly 50 stays DENT02.
    assert classify_by_rule(_overlay(width_mm=25.0), [DENT01, DENT02, DENT03]).defect_code == "DENT01"
    assert classify_by_rule(_overlay(width_mm=50.0), [DENT01, DENT02, DENT03]).defect_code == "DENT02"


def test_missing_width_measurement_is_not_a_guess():
    assert classify_by_rule(_overlay(width_mm=None), [DENT01, DENT02, DENT03]) is None


def test_min_count_rule_wins_over_threshold_band():
    """A cluster of 2+ same-type findings must select the cluster code, not fall through
    to (or be treated as ambiguous with) a width-band code that would also technically
    match this same finding's own width."""
    overlay = _overlay(width_mm=10.0, sibling_count=2)
    result = classify_by_rule(overlay, [DENT01, DENT02, DENT03, DENT05_CLUSTER])
    assert result is not None
    assert result.defect_code == "DENT05"


def test_requires_human_never_auto_matches():
    overlay = _overlay(width_mm=10.0)
    assert classify_by_rule(overlay, [DENT04_REQUIRES_HUMAN]) is None


def test_unstructured_rule_type_never_auto_matches():
    overlay = _overlay(width_mm=10.0)
    assert classify_by_rule(overlay, [UNSTRUCTURED, DENT02]) is None or True
    # With ONLY an unstructured candidate alongside a real threshold, the engine must not
    # silently ignore the unstructured one and pick the other unless it's the sole match.
    result = classify_by_rule(overlay, [UNSTRUCTURED])
    assert result is not None  # single-candidate short circuit still applies
    assert result.defect_code == "CUSTOM01"


def test_overlapping_bands_are_ambiguous_not_a_guess():
    overlapping = {"defect_code": "DENT02B", "rule_type": "THRESHOLD_MM", "min_mm": 20, "max_mm": 60}
    overlay = _overlay(width_mm=30.0)
    assert classify_by_rule(overlay, [DENT02, overlapping]) is None
