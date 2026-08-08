from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.fixture(autouse=True)
def isolate_local_environment(monkeypatch):
    """Keep API tests independent from a developer's private .env file."""
    for name in (
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.asyncio
async def test_mock_seed_and_inspection_flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/health")).json()["mode"] == "mock"
            seeded = await client.post("/api/mock/seed?reset=true")
            assert seeded.status_code == 200
            assert len(seeded.json()) == 6
            assert all(item["source_image_url"].startswith("/assets/train/") for item in seeded.json())

            inspections = await client.get("/api/inspections")
            assert inspections.status_code == 200
            assert len(inspections.json()) == 6
            assert any(item["defects"] for item in inspections.json())
            assert all(item["source_image_url"] for item in inspections.json())
            low_confidence = [
                defect
                for inspection in inspections.json()
                for defect in inspection["defects"]
                if defect["confidence"] < 0.80
            ]
            assert len(low_confidence) == 1
            workflow = await client.get(f"/api/inspections/{seeded.json()[0]['id']}/workflows/latest")
            assert workflow.status_code == 200
            assert workflow.json()["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_create_and_get_inspection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/inspections",
                json={
                    "vin": "TEST-VIN-001",
                    "model": "Test Model",
                    "station": "FNS-01",
                    "defects": [
                        {
                            "defect_type": "dent",
                            "confidence": 0.88,
                            "camera_id": "cam-01",
                            "bbox": {"x1": 10, "y1": 20, "x2": 110, "y2": 180},
                            "location": {"x": 10, "y": 20},
                        }
                    ],
                },
            )
            assert created.status_code == 201
            inspection_id = created.json()["id"]
            fetched = await client.get(f"/api/inspections/{inspection_id}")
            assert fetched.status_code == 200
            assert fetched.json()["defects"][0]["defect_type"] == "dent"
            visible = await client.get("/api/inspections")
            assert visible.json() == []


@pytest.mark.asyncio
async def test_unknown_inspection_returns_404(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/inspections/does-not-exist")
            assert response.status_code == 404


@pytest.mark.asyncio
async def test_mock_yolo_contract_contains_three_defect_classes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/mock/yolo-detections")
            assert response.status_code == 200
            results = response.json()
            detections = [item for result in results for item in result["detections"]]
            assert {item["class_name"] for item in detections} == {"scratch", "dent", "paint_defect"}
            assert all(set(item) >= {"class_id", "class_name", "confidence", "bbox"} for item in detections)
            assert all(set(item["bbox"]) == {"x1", "y1", "x2", "y2"} for item in detections)


@pytest.mark.asyncio
async def test_classify_mock_seed_returns_domain_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            seeded = (await client.post("/api/mock/seed?reset=true")).json()
            for inspection in seeded:
                response = await client.post(f"/api/inspections/{inspection['id']}/classify")
                assert response.status_code == 200
                if inspection["defects"]:
                    item = response.json()[0]
                    assert {"panel", "material", "gdt_group", "tolerance_mm", "measurement_mm", "severity_rank"} <= set(item)
                    assert item["is_mock"] is True


@pytest.mark.asyncio
async def test_decision_engine_returns_expected_mock_actions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            seeded = (await client.post("/api/mock/seed?reset=true")).json()
            results = {}
            for inspection in seeded:
                await client.post(f"/api/inspections/{inspection['id']}/classify")
                decision = await client.post(f"/api/inspections/{inspection['id']}/decide")
                assert decision.status_code == 200
                results[inspection["vin"]] = decision.json()
            assert results["VN9012-2026"]["recommendation"] == "SURFACE_POLISH_REINSPECT"
            assert results["VN8921-2026"]["recommendation"] == "BODY_REPAIR_ASSESSMENT"
            assert results["VN8921-2026"]["test_drive_allowed"] is False


@pytest.mark.asyncio
async def test_decision_without_classification_is_hitl(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/inspections",
                json={
                    "vin": "TEST-HITL-001",
                    "model": "Demo SUV",
                    "defects": [{"defect_type": "dent", "confidence": 0.91, "camera_id": "cam-01"}],
                },
            )
            inspection_id = created.json()["id"]
            workflow = await client.get(f"/api/inspections/{inspection_id}/workflows/latest")
            assert workflow.json()["status"] == "STOPPED_RETRY_REQUIRED"
            assert workflow.json()["decision"] is None


@pytest.mark.asyncio
async def test_hitl_confirm_and_override_are_persisted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            seeded = (await client.post("/api/mock/seed?reset=true")).json()
            scratch = next(item for item in seeded if item["vin"] == "VN9012-2026")
            dent = next(item for item in seeded if item["vin"] == "VN8921-2026")

            await client.post(f"/api/inspections/{scratch['id']}/classify")
            await client.post(f"/api/inspections/{scratch['id']}/decide")
            confirmed = await client.post(
                f"/api/inspections/{scratch['id']}/hitl/reviews",
                json={"reviewer": "qc-inspector-01", "action": "CONFIRM"},
            )
            assert confirmed.status_code == 201
            assert confirmed.json()["final_recommendation"] == "SURFACE_POLISH_REINSPECT"

            await client.post(f"/api/inspections/{dent['id']}/classify")
            await client.post(f"/api/inspections/{dent['id']}/decide")
            overridden = await client.post(
                f"/api/inspections/{dent['id']}/hitl/reviews",
                json={
                    "reviewer": "qc-supervisor-01",
                    "action": "OVERRIDE",
                    "final_recommendation": "SURFACE_POLISH_REINSPECT",
                    "reason": "Mock supervisor exception for demo only",
                },
            )
            assert overridden.status_code == 201
            assert overridden.json()["final_recommendation"] == "SURFACE_POLISH_REINSPECT"


@pytest.mark.asyncio
async def test_hitl_override_requires_reason(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/inspections/any-id/hitl/reviews",
                json={"reviewer": "qc-supervisor-01", "action": "OVERRIDE", "final_recommendation": "SURFACE_POLISH_REINSPECT"},
            )
            assert response.status_code == 422


@pytest.mark.asyncio
async def test_mock_agent_runs_end_to_end_and_persists_trace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            seeded = (await client.post("/api/mock/seed?reset=true")).json()
            scratch = next(item for item in seeded if item["vin"] == "VN9012-2026")
            workflow = await client.post(f"/api/inspections/{scratch['id']}/run-workflow")
            assert workflow.status_code == 201
            result = workflow.json()
            assert result["status"] == "COMPLETED"
            assert result["decision"]["recommendation"] == "SURFACE_POLISH_REINSPECT"
            assert result["decision"]["action_code"] == "SURFACE_POLISH_AND_REINSPECT"
            assert [step["name"] for step in result["steps"]] == ["detect", "validate", "classify", "policy_evaluate", "route", "hitl"]

            saved = await client.get(f"/api/workflows/{result['id']}")
            assert saved.status_code == 200
            assert saved.json()["id"] == result["id"]


@pytest.mark.asyncio
async def test_mock_agent_waits_for_hitl_on_low_confidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/inspections",
                json={
                    "vin": "TEST-LOW-CONFIDENCE-001",
                    "model": "Demo Sedan",
                    "defects": [{"defect_type": "scratch", "confidence": 0.60, "camera_id": "cam-01", "bbox": {"x1": 10, "y1": 20, "x2": 110, "y2": 80}}],
                },
            )
            workflow = await client.post(f"/api/inspections/{created.json()['id']}/run-workflow")
            assert workflow.status_code == 201
            assert workflow.json()["status"] == "WAITING_FOR_HITL"
            assert workflow.json()["hitl_required"] is True


@pytest.mark.asyncio
async def test_train_image_simulation_runs_detector_payload_and_agent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            cases = await client.get("/api/simulations/cases")
            assert cases.status_code == 200
            assert len(cases.json()) == 8
            assert cases.json()[0]["annotation_source"] == "demo_annotation_from_local_train_image"
            assert {item["graph_scenario"] for item in cases.json()} >= {
                "no_defect",
                "high_confidence",
                "medium_confirmed",
                "verify_uncertain",
                "low_confidence",
            }
            assert all(item["panel"] for item in cases.json())
            image_directory = Path(__file__).resolve().parents[1] / "data" / "train"
            assert {item["filename"] for item in cases.json()} == {
                path.name for path in image_directory.glob("*.jpg")
            }

            response = await client.post("/api/simulations/train-21-scratch/run")
            assert response.status_code == 201
            payload = response.json()
            assert payload["inspection"]["station"] == "FNS Line - HA"
            assert payload["workflow"]["decision"]["recommendation"] == "MANUAL_VISUAL_REINSPECTION"
            assert payload["workflow"]["status"] == "WAITING_FOR_HITL"
            assert payload["workflow"]["steps"][0]["name"] == "detect"

            failed = await client.post(
                "/api/simulations/train-21-scratch/run",
                json={"fail_at_step": "classify"},
            )
            assert failed.status_code == 201
            assert failed.json()["workflow"]["status"] == "STOPPED_RETRY_REQUIRED"
            assert failed.json()["workflow"]["decision"] is None
            assert failed.json()["workflow"]["steps"][-1]["error_code"] == "SIMULATED_CLASSIFY_FAILURE"
