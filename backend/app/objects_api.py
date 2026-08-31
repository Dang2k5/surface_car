from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from agent.services.object_storage import ObjectNotFoundError

router = APIRouter(prefix="/assets", tags=["Object storage"])

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


@router.get("/objects/{key:path}")
def get_object(request: Request, key: str) -> Response:
    """Stream one evidence object from the configured backend (local disk
    or AWS S3).

    This URL is stable and never expires, unlike a raw presigned S3 URL —
    it is the "backend proxy" referenced by ENVIRONMENT.md Object Storage
    ("Frontend chi truy cap anh qua backend proxy hoac presigned URL do
    backend cap"). Safe to persist in agent_graph_runs.state_json for
    long-term QC audit history.

    Honors HTTP Range requests (206 Partial Content) — without this, the
    <video> elements in CameraFeed/ImageLightbox cannot seek: browsers
    disable scrubbing on a video served without Accept-Ranges/range support.
    """
    try:
        data, content_type = request.app.state.object_storage.get(key)
    except ObjectNotFoundError as error:
        raise HTTPException(status_code=404, detail="Object not found") from error

    total = len(data)
    range_header = request.headers.get("range")
    if range_header is None:
        return Response(
            content=data,
            media_type=content_type,
            headers={"Accept-Ranges": "bytes"},
        )

    match = _RANGE_RE.match(range_header)
    if not match:
        raise HTTPException(status_code=416, detail="Invalid Range header")
    start_str, end_str = match.groups()
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else total - 1
    end = min(end, total - 1)
    if start > end or start >= total:
        raise HTTPException(
            status_code=416,
            detail="Range not satisfiable",
            headers={"Content-Range": f"bytes */{total}"},
        )

    chunk = data[start : end + 1]
    return Response(
        content=chunk,
        media_type=content_type,
        status_code=206,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{total}",
            "Content-Length": str(len(chunk)),
        },
    )
