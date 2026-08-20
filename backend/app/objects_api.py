from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from agent.services.object_storage import ObjectNotFoundError

router = APIRouter(prefix="/assets", tags=["Object storage"])


@router.get("/objects/{key:path}")
def get_object(request: Request, key: str) -> Response:
    """Stream one evidence object from the configured backend (local disk,
    MinIO, or AWS S3).

    This URL is stable and never expires, unlike a raw presigned S3 URL —
    it is the "backend proxy" referenced by ENVIRONMENT.md Object Storage
    ("Frontend chi truy cap anh qua backend proxy hoac presigned URL do
    backend cap"). Safe to persist in agent_graph_runs.state_json for
    long-term QC audit history.
    """
    try:
        data, content_type = request.app.state.object_storage.get(key)
    except ObjectNotFoundError as error:
        raise HTTPException(status_code=404, detail="Object not found") from error
    return Response(content=data, media_type=content_type)
