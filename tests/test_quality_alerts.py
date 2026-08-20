from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


async def _run_repeated_dent(client: AsyncClient, vehicle_id: str) -> None:
    response = await client.post(
        "/inspections",
        json={
            "vehicle_id": vehicle_id,
            "image_url": "/test-fixtures/repeated-dent.jpg",
            "camera_id": "cam-upstream-01",
            "zone_name": "front_door_outer",
        },
    )
    assert response.status_code == 201
    assert response.json()["state"]["defect_type"] == "dent"


async def _run_confirmed_scratch(client: AsyncClient, vehicle_id: str) -> None:
    response = await client.post(
        "/inspections",
        json={
            "vehicle_id": vehicle_id,
            "image_url": "/test-fixtures/medium_confirmed.jpg",
            "camera_id": "cam-upstream-01",
            "zone_name": "front_door_outer",
        },
    )
    assert response.status_code == 201
    assert response.json()["state"]["defect_type"] == "scratch"


@pytest.mark.asyncio
async def test_repeated_defect_alert_threshold_and_docx_download(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _run_repeated_dent(client, "TREND-CAR-001")
            await _run_repeated_dent(client, "TREND-CAR-002")

            below_threshold = await client.get("/api/quality-alerts")
            assert below_threshold.status_code == 200
            assert below_threshold.json()["alerts"] == []

            await _run_repeated_dent(client, "TREND-CAR-003")
            response = await client.get("/api/quality-alerts")
            assert response.status_code == 200
            summary = response.json()
            assert summary["analyzed_inspections"] == 3
            assert summary["defect_breakdown"][0]["defect_type"] == "dent"
            assert summary["defect_breakdown"][0]["occurrence_count"] == 3
            assert len(summary["findings"]) == 3
            assert len(summary["alerts"]) == 1
            alert = summary["alerts"][0]
            assert alert["severity"] == "CRITICAL"
            assert alert["defect_type"] == "dent"
            assert alert["zone_name"] == "front_door_outer"
            assert alert["camera_id"] == "cam-upstream-01"
            assert alert["affected_vehicle_count"] == 3
            assert alert["window_size"] == 10
            assert alert["consecutive_count"] == 3
            assert alert["trigger_type"] == "CONSECUTIVE"
            assert alert["actionable_routing_command"] == (
                "ROUTE_AFFECTED_BATCH_TO_OFFLINE_INSPECTION_BUFFER"
            )
            assert len(alert["occurrences"]) == 3
            assert {item["inspection_id"] for item in alert["occurrences"]}
            assert {item["vehicle_id"] for item in alert["occurrences"]} == {
                "TREND-CAR-001",
                "TREND-CAR-002",
                "TREND-CAR-003",
            }
            assert "3 xe liên tiếp" in alert["message_vi"]
            assert alert["policy_decision"]["policy_id"] == "FNS-TREND-001"
            assert alert["policy_decision"]["production_eligible"] is False
            assert alert["ai_analysis"]["provider"] == "deterministic"

            report = await client.get("/api/quality-alerts/report.docx")
            assert report.status_code == 200
            assert report.headers["content-type"].startswith(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            assert "attachment" in report.headers["content-disposition"]
            assert report.content.startswith(b"PK")
            assert len(report.content) > 10_000
            with ZipFile(BytesIO(report.content)) as archive:
                report_xml = archive.read("word/document.xml").decode("utf-8")
            assert "Defect summary from inspection history" in report_xml
            assert "Inspection-level findings" in report_xml
            assert "TREND-CAR-003" in report_xml


@pytest.mark.asyncio
async def test_five_vehicles_raise_critical_alert(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for index in range(5):
                await _run_repeated_dent(client, f"CRITICAL-CAR-{index:03d}")
            alert = (await client.get("/api/quality-alerts")).json()["alerts"][0]
            assert alert["severity"] == "CRITICAL"
            assert alert["affected_vehicle_count"] == 5


@pytest.mark.asyncio
async def test_four_matches_in_ten_trigger_warning_without_three_consecutive(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _run_repeated_dent(client, "WINDOW-DENT-001")
            await _run_repeated_dent(client, "WINDOW-DENT-002")
            await _run_confirmed_scratch(client, "WINDOW-SCRATCH-001")
            await _run_repeated_dent(client, "WINDOW-DENT-003")
            await _run_repeated_dent(client, "WINDOW-DENT-004")

            alerts = (await client.get("/api/quality-alerts")).json()["alerts"]
            dent_alert = next(item for item in alerts if item["defect_type"] == "dent")
            assert dent_alert["severity"] == "WARNING"
            assert dent_alert["consecutive_count"] == 2
            assert dent_alert["affected_vehicle_count"] == 4
            assert dent_alert["trigger_type"] == "WINDOW_FREQUENCY"
