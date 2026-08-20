from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def use_fast_mock_detector_for_automated_tests(monkeypatch, tmp_path):
    """Production uses best.pt; unit/API tests keep deterministic injected fakes."""
    monkeypatch.setenv("DETECTOR_PROVIDER", "mock")
    monkeypatch.setenv("QC_REASONING_PROVIDER", "deterministic")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("AUDIT_AUTO_EXPORT_ENABLED", "true")
    monkeypatch.setenv("AUDIT_EXPORT_DIR", str(tmp_path / "audit-exports"))
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite:///{(tmp_path / 'visual-qc-test.db').as_posix()}",
    )
