"""Regression tests for RepetitionAlertService's root-cause hypothesis (PRD.md §6.1):

Root cause must stay a "giả thuyết cần QC xác minh" tied to genuine evidence, not a canned
string keyed only on defect_type. Naming a specific equipment mechanism (as opposed to a
generic "not enough evidence yet" hypothesis) requires ALL THREE independent signals:
coordinate clustering, single-camera consistency, and at least WARNING-tier severity (not a
bare 2-vehicle WATCH coincidence). Any one missing must fall back to the generic hypothesis.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.services.policy import PolicyCatalog
from backend.app.quality_alerts import RepetitionAlertService


class _Repository:
    def __init__(self, states: list[dict[str, Any]]) -> None:
        self._states = states

    def list_with_metadata(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]:
        return self._states[offset : offset + limit] if limit is not None else self._states[offset:]


def _state(
    *,
    vehicle_id: str,
    center_x: float,
    center_y: float,
    defect_type: str = "dent",
    zone_name: str = "door_front_left_class_a",
    camera_id: str = "CAM-01",
) -> dict[str, Any]:
    return {
        "inspection_id": f"INSP-{vehicle_id}",
        "thread_id": f"THREAD-{vehicle_id}",
        "vehicle_id": vehicle_id,
        "_persisted_at": datetime.now(UTC).isoformat(),
        "defect_detected": True,
        "defect_type": defect_type,
        "zone_name": zone_name,
        "camera_id": camera_id,
        "confidence": 0.9,
        "decision": "FAIL",
        "final_status": "FAIL",
        "severity": "B",
        "classified_defect_code": "DENT02" if defect_type == "dent" else "SCRATCH02",
        "recommendation_code": "ROUTE_TO_REWORK",
        "recommendation": "Rework",
        "image_url": "",
        "primary_detection_id": "d1",
        "detections": [
            {
                "detection_id": "d1",
                "visual_measurements": {"center_x_ratio": center_x, "center_y_ratio": center_y},
            }
        ],
    }


def test_tight_coordinate_cluster_confirms_specific_hypothesis() -> None:
    states = [
        _state(vehicle_id="V1", center_x=0.50, center_y=0.40),
        _state(vehicle_id="V2", center_x=0.51, center_y=0.41),
        _state(vehicle_id="V3", center_x=0.49, center_y=0.39),
    ]
    service = RepetitionAlertService(_Repository(states), PolicyCatalog(), reasoning=None)

    summary = service.analyze()

    alert = next(a for a in summary.alerts if a.defect_type == "dent")
    assert alert.root_cause_evidence == "COORDINATE_CLUSTER_CONFIRMED"
    assert alert.root_cause_evidence_detail == {
        "coordinate_cluster": True,
        "single_camera": True,
        "severity_at_least_warning": True,
        "occurrence_count": 3,
    }
    assert "khuôn dập" in alert.predicted_root_cause


def test_scattered_positions_in_same_zone_do_not_confirm_a_mechanism() -> None:
    states = [
        _state(vehicle_id="V1", center_x=0.10, center_y=0.15),
        _state(vehicle_id="V2", center_x=0.85, center_y=0.80),
        _state(vehicle_id="V3", center_x=0.45, center_y=0.55),
    ]
    service = RepetitionAlertService(_Repository(states), PolicyCatalog(), reasoning=None)

    summary = service.analyze()

    alert = next(a for a in summary.alerts if a.defect_type == "dent")
    assert alert.root_cause_evidence == "ZONE_ONLY_UNCONFIRMED"
    assert alert.root_cause_evidence_detail["coordinate_cluster"] is False
    assert "chưa đủ bằng chứng" in alert.predicted_root_cause


def test_tight_cluster_across_different_cameras_does_not_confirm_a_mechanism() -> None:
    """Same coordinate on paper, but seen by different camera rigs -- weaker evidence than a
    single fixed camera repeatedly seeing the same physical spot, so it must NOT confirm."""
    states = [
        _state(vehicle_id="V1", center_x=0.50, center_y=0.40, camera_id="CAM-01"),
        _state(vehicle_id="V2", center_x=0.51, center_y=0.41, camera_id="CAM-02"),
        _state(vehicle_id="V3", center_x=0.49, center_y=0.39, camera_id="CAM-01"),
    ]
    service = RepetitionAlertService(_Repository(states), PolicyCatalog(), reasoning=None)

    summary = service.analyze()

    alert = next(a for a in summary.alerts if a.defect_type == "dent")
    assert alert.root_cause_evidence == "ZONE_ONLY_UNCONFIRMED"
    assert alert.root_cause_evidence_detail["coordinate_cluster"] is True
    assert alert.root_cause_evidence_detail["single_camera"] is False


def test_watch_tier_two_vehicle_coincidence_does_not_confirm_a_mechanism() -> None:
    """Tight cluster + single camera, but only 2 vehicles (WATCH tier) -- too small a sample
    to name specific hardware over."""
    states = [
        _state(vehicle_id="V1", center_x=0.50, center_y=0.40),
        _state(vehicle_id="V2", center_x=0.51, center_y=0.41),
    ]
    service = RepetitionAlertService(_Repository(states), PolicyCatalog(), reasoning=None)

    summary = service.analyze()

    alert = next(a for a in summary.alerts if a.defect_type == "dent")
    assert alert.severity == "WATCH"
    assert alert.root_cause_evidence == "ZONE_ONLY_UNCONFIRMED"
    assert alert.root_cause_evidence_detail["severity_at_least_warning"] is False
