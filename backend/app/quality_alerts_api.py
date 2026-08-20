from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

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
    minimum_occurrences: int,
    in_window_threshold: int,
) -> QualityAlertSummary:
    service = RepetitionAlertService(
        request.app.state.qc_repository,
        request.app.state.qc_policy_catalog,
        request.app.state.qc_reasoning,
    )
    return service.analyze(
        window_hours=window_hours,
        window_size=window_size,
        minimum_occurrences=minimum_occurrences,
        in_window_threshold=in_window_threshold,
    )


@router.get("", response_model=QualityAlertSummary)
def list_quality_alerts(
    request: Request,
    window_hours: int = Query(default=24, ge=1, le=720),
    window_size: int = Query(default=10, ge=4, le=100),
    minimum_occurrences: int = Query(default=3, ge=2, le=20),
    in_window_threshold: int = Query(default=4, ge=2, le=100),
) -> QualityAlertSummary:
    return _summary(
        request,
        window_hours,
        window_size,
        minimum_occurrences,
        in_window_threshold,
    )


@router.get("/report.docx")
def download_quality_alert_report(
    request: Request,
    window_hours: int = Query(default=24, ge=1, le=720),
    window_size: int = Query(default=10, ge=4, le=100),
    minimum_occurrences: int = Query(default=3, ge=2, le=20),
    in_window_threshold: int = Query(default=4, ge=2, le=100),
) -> StreamingResponse:
    summary = _summary(
        request,
        window_hours,
        window_size,
        minimum_occurrences,
        in_window_threshold,
    )
    filename = quote("visual-qc-repeated-defect-alert.docx")
    return StreamingResponse(
        build_quality_alert_report(summary),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
