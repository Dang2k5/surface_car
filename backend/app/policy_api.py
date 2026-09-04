from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError

from .auth import CurrentUser, get_current_user, require_role
from .qc_schemas import PolicyItemCreate, PolicyItemUpdate, PolicySourceCreate

router = APIRouter(prefix="/api/policies", tags=["QC policy catalog"])

MAX_SOURCE_UPLOAD_BYTES = 15 * 1024 * 1024


@router.get("")
def get_policy_catalog(request: Request, user: CurrentUser = Depends(get_current_user)) -> dict:
    return request.app.state.qc_policy_catalog.public_catalog()


@router.get("/{policy_id}")
def get_policy(
    policy_id: str, request: Request, user: CurrentUser = Depends(get_current_user)
) -> dict:
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


@router.post("/sources", status_code=201)
async def create_source(
    request: Request,
    file: UploadFile,
    id: str = Form(...),
    document_family: str = Form(...),
    revision: str = Form(...),
    section: str = Form(...),
    title: str = Form(...),
    scope: str = Form(...),
    effective_date: str | None = Form(default=None),
    expiry_date: str | None = Form(default=None),
    document_status: str = Form(default="DRAFT"),
    authority: str = Form(default="REFERENCE"),
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict:
    """Register a new controlled-document source together with its file (the
    AI-extract-from-PDF flow, POST /api/policies/extract, only reads the file's text —
    it never writes to storage, so a supervisor who never saves leaves no orphaned
    object). The file is written to object storage here, at the moment the source is
    actually registered, and only then."""
    try:
        fields = PolicySourceCreate(
            id=id,
            document_family=document_family,
            revision=revision,
            section=section,
            title=title,
            scope=scope,
            effective_date=effective_date,
            expiry_date=expiry_date,
            document_status=document_status,
            authority=authority,
        )
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error

    if fields.id in request.app.state.qc_policy_catalog.sources:
        raise HTTPException(status_code=409, detail=f"Source already exists: {fields.id}")

    data = await file.read()
    if len(data) > MAX_SOURCE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File quá lớn (giới hạn 15MB).")
    if not data:
        raise HTTPException(status_code=422, detail="File rỗng.")

    object_key = f"policy-sources/{uuid.uuid4()}/{file.filename or 'source'}"
    request.app.state.object_storage.put(
        object_key, data, file.content_type or "application/octet-stream"
    )

    try:
        return request.app.state.qc_policy_catalog.create_source(
            {**fields.model_dump(exclude_none=True), "url": f"/assets/objects/{object_key}"}
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
