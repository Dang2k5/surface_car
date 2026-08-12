from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def use_fast_mock_detector_for_automated_tests(monkeypatch):
    """Production uses best.pt; unit/API tests keep deterministic injected fakes."""
    monkeypatch.setenv("DETECTOR_PROVIDER", "mock")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
