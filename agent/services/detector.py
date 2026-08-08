from __future__ import annotations

from typing import Any, Protocol

from agent.graph.state import QCState


class DetectorService(Protocol):
    def detect(self, state: QCState) -> dict[str, Any]: ...


class MockDetector:
    """YOLO/segmentation adapter boundary with deterministic demo scenarios."""

    _SCENARIOS: dict[str, dict[str, Any]] = {
        "no_defect": {
            "defect_detected": False,
            "defect_type": "none",
            "confidence": 0.99,
            "bbox": None,
            "severity": "NONE",
        },
        "high_confidence": {
            "defect_detected": True,
            "defect_type": "dent",
            "confidence": 0.94,
            "bbox": {"x1": 220.0, "y1": 145.0, "x2": 405.0, "y2": 365.0},
            "severity": "P",
        },
        "medium_confirmed": {
            "defect_detected": True,
            "defect_type": "scratch",
            "confidence": 0.68,
            "bbox": {"x1": 265.0, "y1": 255.0, "x2": 495.0, "y2": 425.0},
            "severity": "C",
        },
        "verify_uncertain": {
            "defect_detected": True,
            "defect_type": "dent",
            "confidence": 0.63,
            "bbox": {"x1": 85.0, "y1": 265.0, "x2": 375.0, "y2": 510.0},
            "severity": "UNCONFIRMED",
        },
        "low_confidence": {
            "defect_detected": True,
            "defect_type": "scratch",
            "confidence": 0.32,
            "bbox": {"x1": 225.0, "y1": 430.0, "x2": 615.0, "y2": 615.0},
            "severity": "UNCONFIRMED",
        },
    }

    def detect(self, state: QCState) -> dict[str, Any]:
        case_detection = state.get("mock_detection")
        if case_detection:
            return dict(case_detection)
        scenario = state.get("mock_scenario", "high_confidence")
        return dict(self._SCENARIOS.get(scenario, self._SCENARIOS["high_confidence"]))
