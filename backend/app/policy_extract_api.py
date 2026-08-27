from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from agent.services.policy_extractor import DocumentTextExtractionError, extract_text
from agent.services.reasoning import ReasoningUnavailableError

from .auth import CurrentUser, require_role

router = APIRouter(prefix="/api/policies", tags=["QC policy catalog"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def _known_vocabulary(catalog_document: dict) -> dict[str, list[str]]:
    policies = catalog_document.get("policies", [])
    defect_types: set[str] = set()
    required_evidence: set[str] = set()
    steps: set[str] = set()
    action_codes: set[str] = set()
    for policy in policies:
        defect_types.update(policy.get("defect_types", []))
        required_evidence.update(policy.get("required_evidence", []))
        steps.update(policy.get("steps", []))
        if policy.get("action_code"):
            action_codes.add(policy["action_code"])
        action_codes.update((policy.get("action_code_by_defect") or {}).values())
    return {
        "defect_types": sorted(defect_types),
        "required_evidence": sorted(required_evidence),
        "steps": sorted(steps),
        "action_codes": sorted(action_codes),
    }


@router.post("/extract")
async def extract_policy_from_document(
    request: Request,
    file: UploadFile,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict:
    """Upload a QC work-instruction/control-plan document (PDF/DOCX) and get back an
    AI-drafted policy + source-document metadata for the supervisor to review in the
    existing create/edit form (frontend/src/routes/supervisor/rules.tsx).

    The file itself is NOT written to object storage here — only its text is read for
    the LLM. If the supervisor never saves the draft, nothing was ever persisted (no
    orphaned object to clean up). The file is re-uploaded from the browser and only
    written to storage by POST /api/policies/sources, at the moment the source is
    actually registered."""
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File quá lớn (giới hạn 15MB).")
    if not data:
        raise HTTPException(status_code=422, detail="File rỗng.")

    filename = file.filename or "upload"
    try:
        text = extract_text(data, filename)
    except DocumentTextExtractionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    catalog_document = request.app.state.qc_policy_catalog.public_catalog()
    try:
        extraction = request.app.state.qc_reasoning.extract_policy_draft(
            document_text=text,
            filename=filename,
            known_vocabulary=_known_vocabulary(catalog_document),
        )
    except ReasoningUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail=f"LLM không khả dụng để trích xuất policy ({error}). Thử lại sau hoặc nhập tay.",
        ) from error

    return {
        "policy_draft": extraction.policy.model_dump(),
        "source_draft": extraction.source.model_dump(),
        "extraction_notes_vi": extraction.extraction_notes_vi,
        "provider": extraction.provider,
        "model": extraction.model,
    }
