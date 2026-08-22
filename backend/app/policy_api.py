from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .auth import CurrentUser, require_role
from .qc_schemas import PolicyItemCreate, PolicyItemUpdate

router = APIRouter(prefix="/api/policies", tags=["QC policy catalog"])


@router.get("")
def get_policy_catalog(request: Request) -> dict:
    return request.app.state.qc_policy_catalog.public_catalog()


@router.get("/{policy_id}")
def get_policy(policy_id: str, request: Request) -> dict:
    catalog = request.app.state.qc_policy_catalog.public_catalog()
    policy = next((item for item in catalog["policies"] if item["id"] == policy_id), None)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    sources = {item["id"]: item for item in catalog["sources"]}
    return {
        **policy,
        "catalog_revision": catalog["revision"],
        "catalog_status": catalog["status"],
        "approval_scope": catalog.get("approval_scope", "UNSPECIFIED"),
        "references": [sources[item] for item in policy.get("source_ids", []) if item in sources],
    }


@router.post("", status_code=201)
def create_policy(
    payload: PolicyItemCreate,
    request: Request,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict:
    try:
        return request.app.state.qc_policy_catalog.create_policy(
            payload.model_dump(exclude_none=True)
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{policy_id}")
def update_policy(
    policy_id: str,
    payload: PolicyItemUpdate,
    request: Request,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict:
    updated = request.app.state.qc_policy_catalog.update_policy(
        policy_id, payload.model_dump(exclude_unset=True)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return updated


@router.delete("/{policy_id}", status_code=204)
def delete_policy(
    policy_id: str,
    request: Request,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> None:
    if not request.app.state.qc_policy_catalog.delete_policy(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found")
