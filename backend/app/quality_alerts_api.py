from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from .auth import CurrentUser, get_current_user, require_role
from .quality_alerts import (
    QualityAlertSummary,
    RepetitionAlertService,
    build_quality_alert_report,
)

router = APIRouter(prefix="/api/quality-alerts", tags=["Quality trend alerts"])


def _summary(
    request: Request,
    window_hours: int,
    window_size: int,
    watch_consecutive_threshold: int,
    watch_window_threshold: int,
    minimum_occurrences: int,
    in_window_threshold: int,
    critical_consecutive_threshold: int,
    critical_window_threshold: int,
) -> QualityAlertSummary:
    service = RepetitionAlertService(
        request.app.state.qc_repository,
        request.app.state.qc_policy_catalog,
        request.app.state.qc_reasoning,
    )
    return service.analyze(
        window_hours=window_hours,
        window_size=window_size,
        watch_consecutive_threshold=watch_consecutive_threshold,
        watch_window_threshold=watch_window_threshold,
        minimum_occurrences=minimum_occurrences,
        in_window_threshold=in_window_threshold,
        critical_consecutive_threshold=critical_consecutive_threshold,
        critical_window_threshold=critical_window_threshold,
    )


@router.get("", response_model=QualityAlertSummary)
def list_quality_alerts(
    request: Request,
    window_hours: int = Query(default=24, ge=1, le=720),
    window_size: int = Query(default=10, ge=4, le=100),
    watch_consecutive_threshold: int = Query(default=2, ge=2, le=20),
    watch_window_threshold: int = Query(default=2, ge=2, le=100),
    minimum_occurrences: int = Query(default=3, ge=2, le=20),
    in_window_threshold: int = Query(default=4, ge=2, le=100),
    critical_consecutive_threshold: int = Query(default=5, ge=2, le=20),
    critical_window_threshold: int = Query(default=7, ge=2, le=100),
    user: CurrentUser = Depends(get_current_user),
) -> QualityAlertSummary:
    return _summary(
        request,
        window_hours,
        window_size,
        watch_consecutive_threshold,
        watch_window_threshold,
        minimum_occurrences,
        in_window_threshold,
        critical_consecutive_threshold,
        critical_window_threshold,
    )


@router.get("/report.docx")
def download_quality_alert_report(
    request: Request,
    window_hours: int = Query(default=24, ge=1, le=720),
    window_size: int = Query(default=10, ge=4, le=100),
    watch_consecutive_threshold: int = Query(default=2, ge=2, le=20),
    watch_window_threshold: int = Query(default=2, ge=2, le=100),
    minimum_occurrences: int = Query(default=3, ge=2, le=20),
    in_window_threshold: int = Query(default=4, ge=2, le=100),
    critical_consecutive_threshold: int = Query(default=5, ge=2, le=20),
    critical_window_threshold: int = Query(default=7, ge=2, le=100),
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> StreamingResponse:
    summary = _summary(
        request,
        window_hours,
        window_size,
        watch_consecutive_threshold,
        watch_window_threshold,
        minimum_occurrences,
        in_window_threshold,
        critical_consecutive_threshold,
        critical_window_threshold,
    )
    filename = quote("visual-qc-repeated-defect-alert.docx")
    return StreamingResponse(
        build_quality_alert_report(summary),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
