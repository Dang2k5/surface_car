from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.mark.asyncio
async def test_langgraph_api_completes_and_exposes_mermaid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            graph = await client.get("/agent/graph")
            assert graph.status_code == 200
            assert "prepare_input" in graph.json()["mermaid"]
            assert graph.json()["checkpointer"] == "InMemorySaver"

            response = await client.post(
                "/inspections",
                json={
                    "vehicle_id": "CAR-LG-001",
                    "image_url": "/assets/train/mock.jpg",
                    "camera_id": "cam-fns-01",
                    "panel": "door_panel",
                    "mock_scenario": "medium_confirmed",
                },
            )
            assert response.status_code == 201
            body = response.json()
            assert body["status"] == "COMPLETED"
            assert body["state"]["verify_count"] == 1
            assert body["state"]["recommendation_code"] == "SURFACE_POLISH_AND_REINSPECT"
            assert body["state"]["recommendation"] == "Polish the affected surface and perform a documented reinspection"


@pytest.mark.asyncio
async def test_langgraph_api_interrupts_and_resumes_same_thread(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/inspections",
                json={
                    "vehicle_id": "CAR-LG-HITL",
                    "image_url": "/assets/train/mock.jpg",
                    "mock_scenario": "verify_uncertain",
                },
            )
            body = created.json()
            assert body["status"] == "INTERRUPTED"
            assert body["state"]["verify_count"] == 2
            thread_id = body["thread_id"]

            waiting = await client.get(f"/inspections/{thread_id}/state")
            assert waiting.json()["status"] == "INTERRUPTED"

            resumed = await client.post(
                f"/inspections/{thread_id}/resume",
                json={
                    "action": "APPROVE",
                    "reviewer": "qc-test",
                    "reason": "Defect confirmed under controlled lighting.",
                },
            )
            assert resumed.status_code == 200
            result = resumed.json()
            assert result["thread_id"] == thread_id
            assert result["status"] == "COMPLETED"
            assert result["state"]["human_decision"]["action"] == "APPROVE"
            assert result["state"]["final_status"] == "HOLD_FOR_REWORK"


@pytest.mark.asyncio
async def test_langgraph_stream_emits_real_node_updates_and_saves_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/inspections/stream",
                json={
                    "vehicle_id": "CAR-LG-STREAM",
                    "image_url": "/assets/train/mock.jpg",
                    "mock_scenario": "verify_uncertain",
                },
            )
            assert response.status_code == 200
            events = [json.loads(line) for line in response.text.splitlines()]
            nodes = [event["node"] for event in events if event["type"] == "node"]
            assert nodes[:3] == ["prepare_input", "detect_defect", "assess_result"]
            assert nodes.count("verify_defect") == 2
            assert nodes.count("assess_result") == 3
            assert events[-1]["type"] == "result"
            assert events[-1]["status"] == "INTERRUPTED"

            runs = await client.get("/agent/runs")
            assert runs.status_code == 200
            saved = next(item for item in runs.json() if item["vehicle_id"] == "CAR-LG-STREAM")
            assert saved["status"] == "INTERRUPTED"
            assert saved["state"]["final_status"] == "WAITING_FOR_HITL"

            cleared = await client.delete("/agent/runs")
            assert cleared.status_code == 200
            assert cleared.json()["deleted"] == 1
            assert (await client.get("/agent/runs")).json() == []
            stale_thread = await client.get(f"/inspections/{events[-1]['thread_id']}/state")
            assert stale_thread.status_code == 404


@pytest.mark.asyncio
async def test_case_detection_override_reaches_graph_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/inspections",
                json={
                    "vehicle_id": "CAR-CASE-PROFILE",
                    "image_url": "/assets/train/860.jpg",
                    "panel": "front_door_outer",
                    "mock_scenario": "high_confidence",
                    "mock_detection": {
                        "defect_detected": True,
                        "defect_type": "dent",
                        "confidence": 0.92,
                        "bbox": {"x1": 365, "y1": 200, "x2": 610, "y2": 485},
                        "severity": "P",
                    },
                },
            )
            state = response.json()["state"]
            assert state["panel"] == "front_door_outer"
            assert state["confidence"] == 0.92
            assert state["bbox"]["x1"] == 365


@pytest.mark.asyncio
async def test_repeated_vehicle_keeps_only_latest_agent_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "vehicle_id": "CAR-REPEATED",
                "image_url": "/assets/train/mock.jpg",
                "mock_scenario": "high_confidence",
            }
            first = await client.post("/inspections", json=payload)
            second = await client.post("/inspections", json=payload)
            assert first.json()["thread_id"] != second.json()["thread_id"]
            runs = (await client.get("/agent/runs")).json()
            matching = [run for run in runs if run["state"]["vehicle_id"] == "CAR-REPEATED"]
            assert len(matching) == 1
            assert matching[0]["thread_id"] == second.json()["thread_id"]
