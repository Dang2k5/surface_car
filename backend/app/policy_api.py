from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

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
