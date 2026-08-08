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
