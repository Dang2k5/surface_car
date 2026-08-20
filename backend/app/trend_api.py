from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .auth import CurrentUser, require_role

router = APIRouter(prefix="/api", tags=["Historical Trend"])


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
