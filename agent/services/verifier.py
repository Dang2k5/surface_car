from __future__ import annotations

from typing import Any, Protocol

from agent.graph.state import QCState


class VerifierService(Protocol):
    def verify(self, state: QCState) -> dict[str, Any]: ...


class MockVerifier:
    """Second-pass camera/model adapter used by the verification loop."""

    def verify(self, state: QCState) -> dict[str, Any]:
        verify_count = state.get("verify_count", 0) + 1
        if state.get("mock_scenario") == "medium_confirmed":
            return {
                "verify_count": verify_count,
                "verify_result": "CONFIRMED",
                "confidence": 0.92,
                "severity": state.get("severity", "C"),
            }
        return {
            "verify_count": verify_count,
            "verify_result": "UNCERTAIN",
            "confidence": state.get("confidence", 0.0),
            "severity": "UNCONFIRMED",
        }


class ModelVerifier:
    """Runs a real second inference pass and checks class/confidence stability."""

    def __init__(self, detector: Any, *, min_confidence: float = 0.40) -> None:
        self.detector = detector
        self.min_confidence = min_confidence

    def verify(self, state: QCState) -> dict[str, Any]:
        verify_count = state.get("verify_count", 0) + 1
        second_pass = self.detector.detect(state)
        same_class = second_pass.get("defect_type") == state.get("defect_type")
        confidence = float(second_pass.get("confidence", 0.0))
        confirmed = bool(second_pass.get("defect_detected")) and same_class and confidence >= self.min_confidence
        return {
            **second_pass,
            "verify_count": verify_count,
            "verify_result": "CONFIRMED" if confirmed else "UNCERTAIN",
            "severity": state.get("severity", "UNASSESSED") if confirmed else "UNCONFIRMED",
        }
