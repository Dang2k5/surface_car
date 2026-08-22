from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from .auth import CurrentUser, require_role
from .trend_report import build_trend_report

router = APIRouter(prefix="/api", tags=["Historical Trend"])


def _fetch_trend(
    request: Request,
    group_by: str,
    shift_id: str | None,
    lot_id: str | None,
    station_id: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list[dict[str, Any]]:
    try:
        return request.app.state.database.get_trend(
            group_by=group_by,
            shift_id=shift_id,
            lot_id=lot_id,
            station_id=station_id,
            date_from=date_from,
            date_to=date_to,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/trend", response_model=list[dict[str, Any]])
def get_trend(
    request: Request,
    group_by: Literal["hour", "shift", "lot", "day"] = Query("day"),
    shift_id: str | None = Query(default=None),
    lot_id: str | None = Query(default=None),
    station_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> list[dict[str, Any]]:
    """Historical Trend aggregation for the QC_SUPERVISOR dashboard.

    Separate from `GET /api/v1/station/stream-alerts` (Sliding Window
    realtime) per PRD.md §6.3 / API_CONTRACT.md §7.5.
    """
    return _fetch_trend(request, group_by, shift_id, lot_id, station_id, date_from, date_to)


@router.get("/trend/report.docx")
def download_trend_report(
    request: Request,
    group_by: Literal["hour", "shift", "lot", "day"] = Query("day"),
    shift_id: str | None = Query(default=None),
    lot_id: str | None = Query(default=None),
    station_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> StreamingResponse:
    """DOCX export of GET /api/trend for a chosen ngày/ca/lô/trạm scope —
    routine production quality reporting, separate from the repeated-defect
    alert report at GET /api/quality-alerts/report.docx."""
    rows = _fetch_trend(request, group_by, shift_id, lot_id, station_id, date_from, date_to)
    report = build_trend_report(
        rows,
        group_by=group_by,
        shift_id=shift_id,
        lot_id=lot_id,
        station_id=station_id,
        date_from=date_from,
        date_to=date_to,
    )
    filename = quote("bao-cao-chat-luong.docx")
    return StreamingResponse(
        report,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
