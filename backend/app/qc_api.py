from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError

from .auth import CurrentUser, get_current_user, require_role
from .qc_schemas import DefectCodeCreate, DefectCodeUpdate, QCDecisionCreate

router = APIRouter(prefix="/api/qc", tags=["QC records"])


def _with_source(request: Request, row: dict[str, Any]) -> dict[str, Any]:
    """Enrich a defect_catalog row with the document status/title of the policy-catalog
    source it cites — reuses PolicyCatalog.sources (agent/services/policy.py) as the one
    shared source registry instead of duplicating a second one for defect codes."""
    source = request.app.state.qc_policy_catalog.sources.get(row.get("source_id"))
    return {
        **row,
        "source_title": source.get("title") if source else None,
        "source_document_status": source.get("document_status") if source else None,
    }


@router.get("/defect-codes", response_model=list[dict[str, Any]])
def list_defect_codes(request: Request, active_only: bool = True) -> list[dict[str, Any]]:
    rows = request.app.state.database.list_defect_codes(active_only=active_only)
    return [_with_source(request, row) for row in rows]


@router.post("/defect-codes", response_model=dict[str, Any], status_code=201)
def create_defect_code(
    request: Request,
    payload: DefectCodeCreate,
    # Defect catalog is a governance/quality-standard artifact like shifts/stations
    # (catalog_api.py) — only QC_SUPERVISOR manages it, not every authenticated role.
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict[str, Any]:
    try:
        row = request.app.state.database.create_defect_code(payload.model_dump())
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="Defect code already exists") from error
    return _with_source(request, row)


@router.patch("/defect-codes/{defect_code}", response_model=dict[str, Any])
def update_defect_code(
    defect_code: str,
    payload: DefectCodeUpdate,
    request: Request,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict[str, Any]:
    updated = request.app.state.database.update_defect_code(
        defect_code, payload.model_dump(exclude_unset=True)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Defect code not found")
    return _with_source(request, updated)


@router.delete("/defect-codes/{defect_code}", status_code=204)
def delete_defect_code(
    defect_code: str,
    request: Request,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> None:
    try:
        deleted = request.app.state.database.delete_defect_code(defect_code)
    except IntegrityError as error:
        raise HTTPException(
            status_code=409,
            detail="Mã lỗi đã được dùng trong một quyết định QC — không thể xóa cứng, chỉ có thể Tắt.",
        ) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Defect code not found")


@router.get("/decisions", response_model=list[dict[str, Any]])
def list_qc_decisions(
    request: Request,
    inspection_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    return request.app.state.database.list_qc_decisions(inspection_id=inspection_id)


@router.post("/decisions", response_model=dict[str, Any], status_code=201)
def create_qc_decision(
    request: Request,
    payload: QCDecisionCreate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return request.app.state.database.create_qc_decision(payload.model_dump())
    except IntegrityError as error:
        raise HTTPException(status_code=422, detail="Unknown or inactive defect code") from error
