from __future__ import annotations

from fastapi import APIRouter, Depends

from .auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.get("/me")
def get_current_user_profile(user: CurrentUser = Depends(get_current_user)) -> dict[str, object]:
    """Canonical current-user context for the frontend (API_CONTRACT.md §7.7)."""
    return {"user_id": user.user_id, "email": user.email, "role": user.role}
