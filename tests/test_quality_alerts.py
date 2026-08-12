from __future__ import annotations

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
            "panel": "front_door_outer",
        },
    )
    assert response.status_code == 201
    assert response.json()["state"]["defect_type"] == "dent"


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
            assert len(summary["alerts"]) == 1
            alert = summary["alerts"][0]
            assert alert["severity"] == "WARNING"
            assert alert["defect_type"] == "dent"
            assert alert["panel"] == "front_door_outer"
            assert alert["camera_id"] == "cam-upstream-01"
            assert alert["affected_vehicle_count"] == 3
            assert "công đoạn phía trước" in alert["message_vi"]

            report = await client.get("/api/quality-alerts/report.docx")
            assert report.status_code == 200
            assert report.headers["content-type"].startswith(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            assert "attachment" in report.headers["content-disposition"]
            assert report.content.startswith(b"PK")
            assert len(report.content) > 10_000


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
