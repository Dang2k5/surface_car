from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError

from .auth import CurrentUser, get_current_user
from .qc_schemas import DefectCodeCreate, QCDecisionCreate

router = APIRouter(prefix="/api/qc", tags=["QC records"])


@router.get("/defect-codes", response_model=list[dict[str, Any]])
def list_defect_codes(request: Request, active_only: bool = True) -> list[dict[str, Any]]:
    return request.app.state.database.list_defect_codes(active_only=active_only)


@router.post("/defect-codes", response_model=dict[str, Any], status_code=201)
def create_defect_code(
    request: Request,
    payload: DefectCodeCreate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return request.app.state.database.create_defect_code(payload.model_dump())
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="Defect code already exists") from error


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
