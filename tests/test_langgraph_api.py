from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app, configure_optional_langsmith_tracing

ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_langsmith_tracing_is_offline_by_default(monkeypatch):
    monkeypatch.setenv("ENABLE_LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")

    configure_optional_langsmith_tracing()

    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"


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
                    "image_url": "/test-fixtures/medium_confirmed.jpg",
                    "camera_id": "cam-fns-01",
                    "location": "left_front_door_lower_edge",
                    "length_mm": 18.4,
                },
            )
            assert response.status_code == 201
            body = response.json()
            assert body["status"] == "COMPLETED"
            assert body["state"]["verify_count"] == 0
            assert body["state"]["recommendation_code"] == "SURFACE_DAMAGE_ASSESSMENT_AND_REINSPECT"
            assert body["state"]["recommendation"] == "Hold for controlled surface assessment and documented reinspection"


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
                    "image_url": "/test-fixtures/unknown_defect.jpg",
                },
            )
            body = created.json()
            assert body["status"] == "INTERRUPTED"
            assert body["state"]["verify_count"] == 0
            thread_id = body["thread_id"]

            waiting = await client.get(f"/inspections/{thread_id}/state")
            assert waiting.json()["status"] == "INTERRUPTED"

            resumed = await client.post(
                f"/inspections/{thread_id}/resume",
                json={
                    "action": "APPROVE",
                    "reviewer": "qc-test",
                    "reason": "Defect confirmed under controlled lighting.",
                    "defect_code": "DENT01",
                    "severity": "B",
                    "location": "left_front_door_lower_edge",
                    "length_mm": 18.4,
                    "disposition": "REWORK",
                    "notes": "Confirmed against the controlled defect catalog.",
                },
            )
            assert resumed.status_code == 200
            result = resumed.json()
            assert result["thread_id"] == thread_id
            assert result["status"] == "COMPLETED"
            assert result["state"]["human_decision"]["action"] == "APPROVE"
            assert result["state"]["final_status"] == "HOLD_FOR_REWORK"
            assert result["state"]["qc_decision_record"]["defect_code"] == "DENT01"
            assert result["state"]["qc_decision_record"]["location"] == "left_front_door_lower_edge"
            assert result["state"]["qc_decision_record"]["length_mm"] == 18.4
            assert result["state"]["measurements"]["defect_length_mm"] == 18.4
            decisions = await client.get(
                "/api/qc/decisions",
                params={"inspection_id": result["state"]["inspection_id"]},
            )
            assert decisions.status_code == 200
            assert decisions.json()[0]["disposition"] == "REWORK"


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
                    "image_url": "/test-fixtures/unknown_defect.jpg",
                },
            )
            assert response.status_code == 200
            events = [json.loads(line) for line in response.text.splitlines()]
            nodes = [event["node"] for event in events if event["type"] == "node"]
            assert nodes[:4] == [
                "prepare_input",
                "detect_defect",
                "multimodal_verify",
                "assess_result",
            ]
            assert nodes.count("verify_defect") == 0
            assert nodes.count("assess_result") == 1
            assert events[-1]["type"] == "result"
            assert events[-1]["status"] == "INTERRUPTED"

            runs = await client.get("/agent/runs")
            assert runs.status_code == 200
            saved = next(item for item in runs.json() if item["state"]["vehicle_id"] == "CAR-LG-STREAM")
            assert saved["status"] == "INTERRUPTED"
            assert saved["state"]["final_status"] == "WAITING_FOR_HITL"

            cleared = await client.delete("/agent/runs")
            assert cleared.status_code == 200
            assert cleared.json()["deleted"] == 1
            assert (await client.get("/agent/runs")).json() == []
            stale_thread = await client.get(f"/inspections/{events[-1]['thread_id']}/state")
            assert stale_thread.status_code == 404


@pytest.mark.asyncio
async def test_repeated_vehicle_keeps_only_latest_agent_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "vehicle_id": "CAR-REPEATED",
                "image_url": "/test-fixtures/inspection.jpg",
            }
            first = await client.post("/inspections", json=payload)
            second = await client.post("/inspections", json=payload)
            assert first.json()["thread_id"] != second.json()["thread_id"]
            runs = (await client.get("/agent/runs")).json()
            matching = [run for run in runs if run["state"]["vehicle_id"] == "CAR-REPEATED"]
            assert len(matching) == 1
            assert matching[0]["thread_id"] == second.json()["thread_id"]


@pytest.mark.asyncio
async def test_agent_audit_exports_json_and_jsonl_without_local_image_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/inspections",
                json={
                    "vehicle_id": "CAR-EXPORT-001",
                    "image_paths": [r"C:\\private-workstation\\evidence.jpg"],
                    "camera_id": "cam-export",
                },
            )
            assert created.status_code == 201
            thread_id = created.json()["thread_id"]

            automatic_file = tmp_path / "audit-exports" / f"visual-qc-inspection-{thread_id}.json"
            assert automatic_file.is_file()
            automatic_audit = json.loads(automatic_file.read_text(encoding="utf-8"))
            assert automatic_audit["identity"]["thread_id"] == thread_id
            assert automatic_audit["identity"]["status"] == "HOLD_FOR_REWORK"
            assert "image_paths" not in automatic_file.read_text(encoding="utf-8")

            single = await client.get(f"/agent/runs/{thread_id}/export.json")
            assert single.status_code == 200
            assert "attachment" in single.headers["content-disposition"]
            audit = single.json()
            assert audit["schema"] == "visual-qc-agent-audit/v1"
            assert audit["identity"]["thread_id"] == thread_id
            assert audit["workflow"]["execution_trace"]
            assert audit["policy"]
            assert audit["reasoning"]
            assert "image_paths" not in single.text
            assert "private-workstation" not in single.text

            collection = await client.get("/agent/runs/export.jsonl")
            assert collection.status_code == 200
            assert "attachment" in collection.headers["content-disposition"]
            records = [json.loads(line) for line in collection.text.splitlines()]
            assert len(records) == 1
            assert records[0]["identity"]["thread_id"] == thread_id

            missing = await client.get("/agent/runs/not-found/export.json")
            assert missing.status_code == 404


@pytest.mark.asyncio
async def test_hitl_resume_updates_the_same_automatic_audit_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/inspections",
                json={
                    "vehicle_id": "CAR-AUTO-EXPORT-HITL",
                    "image_url": "/test-fixtures/unknown_defect.jpg",
                },
            )
            thread_id = created.json()["thread_id"]
            automatic_file = tmp_path / "audit-exports" / f"visual-qc-inspection-{thread_id}.json"
            waiting = json.loads(automatic_file.read_text(encoding="utf-8"))
            assert waiting["identity"]["status"] == "WAITING_FOR_HITL"

            resumed = await client.post(
                f"/inspections/{thread_id}/resume",
                json={
                    "action": "APPROVE",
                    "reviewer": "qc-test",
                    "reason": "Defect confirmed during controlled QC review.",
                },
            )
            assert resumed.status_code == 200
            completed = json.loads(automatic_file.read_text(encoding="utf-8"))
            assert completed["identity"]["status"] == "HOLD_FOR_QC"
            assert completed["workflow"]["human_decision"]["action"] == "APPROVE"


@pytest.mark.asyncio
async def test_web_image_upload_is_validated_saved_and_sent_to_graph(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/inspections/from-image",
                data={
                    "vehicle_id": "CAR-WEB-UPLOAD",
                    "camera_id": "cam-web",
                    "zone_name": "front_door_outer",
                },
                files={"file": ("evidence.png", ONE_PIXEL_PNG, "image/png")},
            )
            assert response.status_code == 201
            state = response.json()["state"]
            assert state["vehicle_id"] == "CAR-WEB-UPLOAD"
            assert state["zone_name"] == "front_door_outer"
            assert "recommended_plan" not in state
            assert "final_action" not in state
            assert state["image_url"].startswith("/assets/objects/inspections/")
            assert len(state["image_sha256"]) == 64
            assert state["decision"] == "DEFECT_CONFIRMED"
            # The scratch file used for local YOLO inference is deleted right
            # after graph.invoke(); the durable copy lives in object storage
            # and is served back through the same proxy URL.
            assert not Path(state["image_paths"][0]).exists()
            evidence = await client.get(state["image_url"])
            assert evidence.status_code == 200
            assert evidence.content == ONE_PIXEL_PNG


@pytest.mark.asyncio
async def test_v1_inspect_contract_wraps_the_langgraph_workflow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/inspect",
                data={
                    "vehicle_id": "CAR-V1-001",
                    "station_id": "FNS_LINE_HA_01",
                    "zone_name": "front_door_outer",
                },
                files={"file": ("evidence.png", ONE_PIXEL_PNG, "image/png")},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is True
            assert payload["vehicle_id"] == "CAR-V1-001"
            assert payload["result"]["recommended_plan"] in {
                "PASS",
                "PLAN_A_BUFFING",
                "PLAN_B_HOLD",
            }
            assert payload["result"]["concrete_action"]
            assert payload["result"]["defects"][0]["estimated_depth_mm"] is None
            assert payload["result"]["defects"][0]["physical_measurement_status"] == (
                "REQUIRES_CALIBRATION_OR_QC_MEASUREMENT"
            )


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
async def test_multi_camera_upload_runs_one_aggregated_vehicle_inspection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/inspections/from-images",
                data={
                    "vehicle_id": "CAR-MULTI-CAMERA",
                    "camera_ids": ["CAM-FNS-FRONT", "CAM-FNS-REAR"],
                },
                files=[
                    ("files", ("front.png", ONE_PIXEL_PNG, "image/png")),
                    ("files", ("rear.png", ONE_PIXEL_PNG, "image/png")),
                ],
            )
            assert response.status_code == 201
            state = response.json()["state"]
            assert [item["camera_id"] for item in state["camera_evidence"]] == [
                "CAM-FNS-FRONT",
                "CAM-FNS-REAR",
            ]
            assert len(state["camera_results"]) == 2
            assert state["finding_groups"][0]["observation_count"] == 2
            assert state["finding_groups"][0]["deduplication_status"] == (
                "CANDIDATE_DUPLICATE_REQUIRES_CALIBRATION"
            )
            # Scratch files used for local YOLO inference are deleted right
            # after graph.invoke(); each camera's durable copy lives in
            # object storage and is served back through the same proxy URLs.
            for item in state["camera_evidence"]:
                assert not Path(item["image_path"]).exists()
                evidence = await client.get(item["image_url"])
                assert evidence.status_code == 200


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
