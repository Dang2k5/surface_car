from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from .auth import CurrentUser, get_current_user, require_role
from .qc_schemas import ProfileUpdate

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.get("/me")
def get_current_user_profile(user: CurrentUser = Depends(get_current_user)) -> dict[str, object]:
    """Canonical current-user context for the frontend (API_CONTRACT.md §7.7)."""
    return {
        "user_id": user.user_id,
        "email": user.email,
        "role": user.role,
        "station_id": user.station_id,
    }


@router.get("/profiles", response_model=list[dict[str, Any]])
def list_profiles(
    request: Request,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> list[dict[str, Any]]:
    """Account management: every known inspector/supervisor profile, for the Supervisor's
    account management screen (which station each inspector belongs to, and their role)."""
    return request.app.state.database.list_profiles()


@router.patch("/profiles/{user_id}", response_model=dict[str, Any])
def update_profile(
    user_id: str,
    request: Request,
    payload: ProfileUpdate,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict[str, Any]:
    """Reassign an inspector's station or change their role (e.g. promote to QC_SUPERVISOR
    on a staff rotation). Supervisor-only, mirrors backend/app/catalog_api.py's station CRUD."""
    database = request.app.state.database
    patch = payload.model_dump(exclude_unset=True)
    if "station_id" in patch and patch["station_id"] and database.get_station(patch["station_id"]) is None:
        raise HTTPException(status_code=422, detail=f"Không tìm thấy trạm: {patch['station_id']}")
    if "role" in patch and patch["role"] != user.role and user_id == user.user_id:
        raise HTTPException(status_code=400, detail="Không thể tự thay đổi vai trò của chính mình.")
    updated = database.update_profile(user_id, patch)
    if updated is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
    return updated
