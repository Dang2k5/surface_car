import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.mark.asyncio
async def test_mock_seed_and_inspection_flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/health")).json()["mode"] == "mock"
            seeded = await client.post("/api/mock/seed?reset=true")
            assert seeded.status_code == 200
            assert len(seeded.json()) == 11

            inspections = await client.get("/api/inspections")
            assert inspections.status_code == 200
            assert len(inspections.json()) == 11
            assert any(item["defects"] for item in inspections.json())
            low_confidence = [
                defect
                for inspection in inspections.json()
                for defect in inspection["defects"]
                if defect["confidence"] < 0.80
            ]
            assert len(low_confidence) == 6
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
            assert results["MOCK-VIN-SCRATCH-001"]["recommendation"] == "PLAN_A"
            assert results["MOCK-VIN-DENT-001"]["recommendation"] == "PLAN_B"
            assert results["MOCK-VIN-PAINT-001"]["recommendation"] == "PLAN_B"
            assert results["MOCK-VIN-PASS-001"]["recommendation"] == "PASS"
            assert results["MOCK-VIN-DENT-001"]["test_drive_allowed"] is False


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
            assert workflow.json()["decision"]["recommendation"] == "PLAN_B"
            assert workflow.json()["decision"]["test_drive_allowed"] is False


@pytest.mark.asyncio
async def test_hitl_confirm_and_override_are_persisted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            seeded = (await client.post("/api/mock/seed?reset=true")).json()
            scratch = next(item for item in seeded if item["vin"] == "MOCK-VIN-SCRATCH-001")
            dent = next(item for item in seeded if item["vin"] == "MOCK-VIN-DENT-001")

            await client.post(f"/api/inspections/{scratch['id']}/classify")
            await client.post(f"/api/inspections/{scratch['id']}/decide")
            confirmed = await client.post(
                f"/api/inspections/{scratch['id']}/hitl/reviews",
                json={"reviewer": "qc-inspector-01", "action": "CONFIRM"},
            )
            assert confirmed.status_code == 201
            assert confirmed.json()["final_recommendation"] == "PLAN_A"

            await client.post(f"/api/inspections/{dent['id']}/classify")
            await client.post(f"/api/inspections/{dent['id']}/decide")
            overridden = await client.post(
                f"/api/inspections/{dent['id']}/hitl/reviews",
                json={
                    "reviewer": "qc-supervisor-01",
                    "action": "OVERRIDE",
                    "final_recommendation": "PLAN_A",
                    "reason": "Mock supervisor exception for demo only",
                },
            )
            assert overridden.status_code == 201
            assert overridden.json()["final_recommendation"] == "PLAN_A"


@pytest.mark.asyncio
async def test_hitl_override_requires_reason(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/inspections/any-id/hitl/reviews",
                json={"reviewer": "qc-supervisor-01", "action": "OVERRIDE", "final_recommendation": "PLAN_A"},
            )
            assert response.status_code == 422


@pytest.mark.asyncio
async def test_mock_agent_runs_end_to_end_and_persists_trace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            seeded = (await client.post("/api/mock/seed?reset=true")).json()
            scratch = next(item for item in seeded if item["vin"] == "MOCK-VIN-SCRATCH-001")
            workflow = await client.post(f"/api/inspections/{scratch['id']}/run-workflow")
            assert workflow.status_code == 201
            result = workflow.json()
            assert result["status"] == "COMPLETED"
            assert result["decision"]["recommendation"] == "PLAN_A"
            assert [step["name"] for step in result["steps"]] == ["detect", "classify", "decide", "hitl"]

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
                    "defects": [{"defect_type": "scratch", "confidence": 0.60, "camera_id": "cam-01"}],
                },
            )
            workflow = await client.post(f"/api/inspections/{created.json()['id']}/run-workflow")
            assert workflow.status_code == 201
            assert workflow.json()["status"] == "WAITING_FOR_HITL"
            assert workflow.json()["hitl_required"] is True


@pytest.mark.asyncio
async def test_agent_explanation_requires_llm_configuration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QC_LLM_API_KEY", raising=False)
    monkeypatch.delenv("QC_LLM_BASE_URL", raising=False)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            seeded = (await client.post("/api/mock/seed?reset=true")).json()
            workflow = await client.post(f"/api/inspections/{seeded[0]['id']}/run-workflow")
            assert workflow.status_code == 201
            response = await client.post(
                f"/api/inspections/{seeded[0]['id']}/agent/explain",
                json={"language": "vi", "question": "Tóm tắt quyết định cho QC."},
            )
            assert response.status_code == 503
