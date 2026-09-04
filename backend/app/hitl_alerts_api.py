from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from .auth import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/api/production-line", tags=["Production line control"])


def _line_status_payload(station_id: str, row: dict[str, Any] | None) -> dict[str, Any]:
    """A station with no row has never been stopped — default to RUNNING rather than
    forcing every caller (including the upload endpoints' gate check) to special-case None."""
    if row is None:
        return {
            "station_id": station_id,
            "status": "RUNNING",
            "stop_reason": None,
            "stopped_by": None,
            "stopped_at": None,
            "resumed_by": None,
            "resumed_at": None,
        }
    return {
        "station_id": row["station_id"],
        "status": row["status"],
        "stop_reason": row.get("stop_reason"),
        "stopped_by": row.get("stopped_by"),
        "stopped_at": row.get("stopped_at"),
        "resumed_by": row.get("resumed_by"),
        "resumed_at": row.get("resumed_at"),
    }


@router.get("/{station_id}/status")
def get_line_status(
    request: Request, station_id: str, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    row = request.app.state.database.get_line_status(station_id)
    return _line_status_payload(station_id, row)


@router.post("/{station_id}/stop")
def stop_line(
    request: Request,
    station_id: str,
    body: dict[str, str] = Body(...),
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict[str, Any]:
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Cần nhập lý do dừng chuyền")
    row = request.app.state.database.stop_line(station_id, user.user_id, reason)
    return _line_status_payload(station_id, row)


@router.post("/{station_id}/resume")
def resume_line(
    request: Request,
    station_id: str,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict[str, Any]:
    row = request.app.state.database.resume_line(station_id, user.user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Trạm này chưa từng bị dừng")
    return _line_status_payload(station_id, row)


@router.get("/{station_id}/hitl-alert")
def get_hitl_alert(
    request: Request, station_id: str, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any] | None:
    alert = request.app.state.hitl_alert_service.analyze(station_id=station_id)
    return alert.model_dump(mode="json") if alert else None
