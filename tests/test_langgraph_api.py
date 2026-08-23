from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app, configure_optional_langsmith_tracing


def test_langsmith_tracing_is_offline_by_default(monkeypatch):
    monkeypatch.setenv("ENABLE_LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")

    configure_optional_langsmith_tracing()

    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"


@pytest.mark.asyncio
async def test_agent_status_distinguishes_llm_from_rule_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/agent/status")
            assert response.status_code == 200
            payload = response.json()
            assert payload["langgraph"] == "READY"
            assert payload["reasoning"]["mode"] == "RULE_BASED"
            assert payload["reasoning"]["llm_accessed"] is False


@pytest.mark.asyncio
async def test_public_api_does_not_expose_legacy_mock_catalog(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/openapi.json")
            assert response.status_code == 200
            document = response.json()
            paths = document["paths"]
            schemas = document["components"]["schemas"]

            assert not any("mock" in path or "evidence/cases" in path for path in paths)
            assert "mock_scenario" not in str(schemas)
            assert "mock_detection" not in str(schemas)
