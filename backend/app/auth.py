from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request

# Requests are treated as authenticated by an unconditionally-trusted dev
# identity whenever SUPABASE_JWT_SECRET is unset (ENVIRONMENT.md: RBAC
# enforcement requires that secret to be configured first). This keeps local
# development and demo runs working exactly as before RBAC existed.
DEV_BYPASS_USER_ID = "dev-bypass"


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    email: str | None
    role: str


def _decode_bearer_token(request: Request, secret: str) -> dict:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Supabase access token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=401, detail="Invalid or expired Supabase access token"
        ) from error


def get_current_user(request: Request) -> CurrentUser:
    """Verify the Supabase access token and resolve the caller's `profiles.role`.

    API_CONTRACT.md §7.7: FastAPI never issues sessions, it only verifies
    Supabase-issued JWTs and looks up role in `profiles`.
    """
    settings = request.app.state.auth_settings
    if not settings.supabase_jwt_secret:
        return CurrentUser(user_id=DEV_BYPASS_USER_ID, email=None, role="QC_SUPERVISOR")
    claims = _decode_bearer_token(request, settings.supabase_jwt_secret)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Supabase access token missing sub claim")
    email = claims.get("email")
    profile = request.app.state.database.get_or_create_profile(
        user_id, email, settings.default_qc_role
    )
    return CurrentUser(user_id=user_id, email=email, role=profile["role"])


def require_role(*roles: str):
    """Dependency factory gating an endpoint to specific `profiles.role` values.

    Bypassed together with `get_current_user` when RBAC is not yet configured.
    """

    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.user_id != DEV_BYPASS_USER_ID and user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(roles)}")
        return user

    return dependency
