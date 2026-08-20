from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from .auth import CurrentUser, get_current_user
from .langgraph_api import run_uploaded_image_inspection
from .quality_alerts import RepetitionAlertService

router = APIRouter(prefix="/api/v1", tags=["Visual QC v1 contract"])


def _alert_service(request: Request) -> RepetitionAlertService:
    return RepetitionAlertService(
        request.app.state.qc_repository,
        request.app.state.qc_policy_catalog,
        request.app.state.qc_reasoning,
    )


@router.post("/inspect")
def inspect_vehicle(
    request: Request,
    file: UploadFile = File(...),
    vehicle_id: str = Form(...),
    station_id: str = Form("FNS_LINE_HA_01"),
    vehicle_model: str = Form("unknown_model"),
    zone_name: str = Form("unknown_zone"),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Compatibility contract backed by the production LangGraph workflow."""
    run = run_uploaded_image_inspection(
        request=request,
        file=file,
        vehicle_id=vehicle_id,
        vehicle_model=vehicle_model,
        camera_id=station_id,
        zone_name=zone_name,
    )
    state = run.state
    summary = _alert_service(request).analyze()
    matching_alert = next(
        (
            item
            for item in summary.alerts
            if item.defect_type == state.get("defect_type")
            and item.zone_name == str(state.get("zone_name") or "unknown_zone")
        ),
        None,
    )
    policy = state.get("policy_decision") or {}
    result_status = (
        "WAITING_QC"
        if run.status == "INTERRUPTED"
        else "PASS"
        if state.get("final_status") == "PASS"
        else "FAIL"
    )
    return {
        "success": True,
        "inspection_id": state.get("inspection_id"),
        "thread_id": run.thread_id,
        "vehicle_id": vehicle_id,
        "result": {
            "status": result_status,
            "recommended_plan": _compatibility_plan(state),
            "concrete_action": state.get("recommendation_code") or state.get("decision"),
            "allow_test_drive": state.get("allow_test_drive", False),
            "rework_destination": state.get("recommendation"),
            "overall_rank": state.get("severity"),
            "reasoning_summary": state.get("reason"),
            "defects": state.get("enriched_defects") or [],
            "systemic_anomaly": matching_alert.model_dump(mode="json") if matching_alert else None,
            "policy": {
                "id": policy.get("policy_id"),
                "revision": policy.get("policy_revision"),
                "status": policy.get("policy_status"),
            },
        },
        "hitl": {
            "status": state.get("hitl_status") or ("PENDING" if run.status == "INTERRUPTED" else "CONFIRMED"),
            "resume_url": f"/inspections/{run.thread_id}/resume" if run.status == "INTERRUPTED" else None,
        },
        "created_at": datetime.now(UTC).isoformat(),
    }


def _compatibility_plan(state: dict[str, Any]) -> str:
    """Legacy PRD alias derived from the canonical recommendation_code."""
    if state.get("final_status") == "PASS":
        return "PASS"
    if state.get("recommendation_code") == "SURFACE_POLISH_AND_REINSPECT":
        return "PLAN_A_BUFFING"
    return "PLAN_B_HOLD"


@router.get("/station/stream-alerts")
async def stream_station_alerts(request: Request) -> StreamingResponse:
    """SSE stream over the database-backed 10-vehicle anomaly window."""

    async def events():
        sent_ids: set[str] = set()
        while not await request.is_disconnected():
            summary = _alert_service(request).analyze()
            for alert in summary.alerts:
                if alert.id in sent_ids:
                    continue
                sent_ids.add(alert.id)
                payload = {
                    "timestamp": summary.generated_at,
                    "station_id": alert.camera_id,
                    "alert_level": alert.severity,
                    "defect_type": alert.defect_type,
                    "zone": alert.zone_name,
                    "consecutive_count": alert.consecutive_count,
                    "affected_vehicle_ids": alert.affected_vehicle_ids,
                    "predicted_root_cause": alert.predicted_root_cause,
                    "upstream_target_shop": alert.upstream_target_shop,
                    "instruction": alert.actionable_routing_command,
                }
                yield "event: systemic_anomaly_alert\n"
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield ": keep-alive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
