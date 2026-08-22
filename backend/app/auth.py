from __future__ import annotations

import logging
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request

logger = logging.getLogger(__name__)

# Requests are treated as authenticated by an unconditionally-trusted dev
# identity whenever Supabase auth isn't configured (no SUPABASE_JWT_SECRET and no
# SUPABASE_URL — ENVIRONMENT.md: RBAC enforcement requires one of those first). This keeps
# local development and demo runs working exactly as before RBAC existed.
DEV_BYPASS_USER_ID = "dev-bypass"


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    email: str | None
    role: str


def _decode_bearer_token(request: Request) -> dict:
    """Verify a Supabase access token, supporting both signing schemes Supabase issues:

    - HS256 with a shared secret (SUPABASE_JWT_SECRET) — legacy projects / self-hosted Supabase.
    - ES256/RS256 verified against the project's JWKS endpoint (app.state.supabase_jwks_client)
      — the default for projects on Supabase's newer API-key system, which has no shared secret.
    """
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Supabase access token")
    token = authorization.removeprefix("Bearer ").strip()
    settings = request.app.state.auth_settings
    jwks_client = getattr(request.app.state, "supabase_jwks_client", None)
    # PyJWT's default leeway is 0, so any clock drift between this machine and Supabase's
    # issuing server rejects a freshly-issued token as "not yet valid" (iat) — a few seconds
    # of skew is normal and not a security concern here, so tolerate it explicitly.
    clock_leeway_seconds = 10
    try:
        if settings.supabase_jwt_secret:
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                leeway=clock_leeway_seconds,
            )
        if jwks_client is not None:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
                leeway=clock_leeway_seconds,
            )
        # Reachable only if get_current_user's dev-bypass check above changes without this
        # branch being updated to match — fail closed rather than silently trusting the token.
        raise HTTPException(status_code=500, detail="Supabase auth is not configured")
    except HTTPException:
        raise
    except jwt.PyJWTError as error:
        logger.warning("Supabase access token rejected: %s: %s", type(error).__name__, error)
        raise HTTPException(
            status_code=401, detail="Invalid or expired Supabase access token"
        ) from error


DEV_BYPASS_ROLES = ("QC_SUPERVISOR", "QC_OPERATOR")


def get_current_user(request: Request) -> CurrentUser:
    """Verify the Supabase access token and resolve the caller's `profiles.role`.

    API_CONTRACT.md §7.7: FastAPI never issues sessions, it only verifies
    Supabase-issued JWTs and looks up role in `profiles`.
    """
    settings = request.app.state.auth_settings
    jwks_client = getattr(request.app.state, "supabase_jwks_client", None)
    if not settings.supabase_jwt_secret and jwks_client is None:
        # Dev-only: let the frontend simulate either role via a plain header
        # so QC screens can be tested locally before real Supabase JWTs exist.
        # Never consulted once Supabase auth is configured (real RBAC path below).
        dev_role = request.headers.get("X-Dev-Role")
        role = dev_role if dev_role in DEV_BYPASS_ROLES else "QC_OPERATOR"
        return CurrentUser(user_id=DEV_BYPASS_USER_ID, email=None, role=role)
    claims = _decode_bearer_token(request)
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

    Still enforced against the simulated role in dev-bypass mode (via
    X-Dev-Role), so the frontend's role switcher behaves the same locally as
    it will once real Supabase JWTs are configured.
    """

    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(roles)}")
        return user

    return dependency
