from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from agent.graph.state import QCState
from agent.services.audit_export import build_audit_export
from agent.services.image_render import render_defect_images
from agent.services.video_processor import (
    VideoProcessor,
    DefectDeduplicator,
    MultiCameraAggregator,
    VideoProcessingError,
)

from .auth import CurrentUser, get_current_user
from .langgraph_schemas import (
    AgentGraphResponse,
    LangGraphInspectionCreate,
    LangGraphResumeRequest,
    LangGraphRunResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["LangGraph Visual QC"])


def _attachment(content: bytes, *, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _interrupt_value(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__", ())
    if not interrupts:
        return None
    value = getattr(interrupts[0], "value", interrupts[0])
    return value if isinstance(value, dict) else {"value": value}


def _graph_response(graph: Any, thread_id: str, result: dict[str, Any]) -> LangGraphRunResponse:
    interrupt_value = _interrupt_value(result)
    snapshot = graph.get_state(_config(thread_id))
    state = dict(snapshot.values)
    return LangGraphRunResponse(
        thread_id=thread_id,
        status="INTERRUPTED" if interrupt_value else "COMPLETED",
        state=state,
        interrupt=interrupt_value,
    )


def _snapshot_interrupt(snapshot: Any) -> dict[str, Any] | None:
    for task in snapshot.tasks or ():
        if task.interrupts:
            value = task.interrupts[0].value
            return value if isinstance(value, dict) else {"value": value}
    return None


def _initial_state(
    payload: LangGraphInspectionCreate,
    thread_id: str,
    settings: Any,
) -> QCState:
    return {
        "thread_id": thread_id,
        "inspection_id": payload.inspection_id or str(uuid4()),
        "vehicle_id": payload.vehicle_id,
        "vehicle_model": payload.vehicle_model,
        "lot_id": payload.lot_id,
        "shift_id": payload.shift_id,
        "production_date": payload.production_date,
        "station_id": payload.station_id,
        "image_url": payload.image_url or "",
        "image_paths": payload.image_paths,
        "camera_id": payload.camera_id,
        "zone_name": payload.zone_name,
        "verify_count": 0,
        "retry_count": 0,
        "max_retries": 2,
        "auto_pass_enabled": settings.auto_pass_enabled,
        "confirmed_threshold": settings.confirmed_threshold,
        "verify_threshold": settings.verify_threshold,
        "execution_trace": [],
    }


def _save_waiting_state(request: Request, state: dict[str, Any]) -> None:
    request.app.state.qc_repository.save({**state, "final_status": "WAITING_FOR_HITL"})


def _write_scratch_image(data: bytes, suffix: str) -> Path:
    """Write uploaded bytes to a private temp file for the local YOLO
    detector to read during this request only.

    The durable copy lives in object storage (ENVIRONMENT.md Object
    Storage), not on local disk — the caller deletes this scratch file
    right after `graph.invoke()` returns.
    """
    fd, raw_path = tempfile.mkstemp(suffix=suffix, prefix="qc-inference-")
    path = Path(raw_path)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return path


def _attach_rendered_defect_images(
    request: Request,
    state: dict[str, Any],
    inspection_id: str,
    scratch_path_by_camera: dict[str, Path],
) -> None:
    """Render overlay/crop/mask PNGs for every detection (not just the primary one) and store
    them in object storage (FR-17, API_CONTRACT.md), so a secondary-camera finding gets its own
    real crop instead of the UI falling back to that camera's uncropped full photo. Skips a
    detection when there is nothing to render for it, and never fails the inspection response
    if rendering one detection fails — the rest still get rendered."""
    primary_detection_id = state.get("primary_detection_id")
    enriched_by_id = {
        item.get("detection_id"): item for item in state.get("enriched_defects") or []
    }
    for detection in state.get("detections") or []:
        detection_id = detection.get("detection_id")
        scratch_path = scratch_path_by_camera.get(str(detection.get("camera_id")))
        if scratch_path is None:
            continue
        try:
            rendered = render_defect_images(scratch_path, detection)
        except Exception:
            logger.warning(
                "Could not render overlay/crop/mask images for inspection %s detection %s",
                inspection_id,
                detection_id,
                exc_info=True,
            )
            continue
        urls = {}
        for name, content in rendered.items():
            object_key = f"inspections/{inspection_id}/{detection_id}/{name}.png"
            request.app.state.object_storage.put(object_key, content, "image/png")
            urls[f"{name}_image_url"] = f"/assets/objects/{object_key}"
        enriched_item = enriched_by_id.get(detection_id)
        if enriched_item is not None:
            enriched_item.update(urls)
        if detection_id == primary_detection_id:
            state.update(urls)


@router.post("/inspections", response_model=LangGraphRunResponse, status_code=201)
@router.post("/api/langgraph/inspections", response_model=LangGraphRunResponse, status_code=201)
def run_langgraph_inspection(
    request: Request,
    payload: LangGraphInspectionCreate,
    user: CurrentUser = Depends(get_current_user),
) -> LangGraphRunResponse:
    graph = request.app.state.qc_langgraph
    thread_id = str(uuid4())
    initial_state = _initial_state(payload, thread_id, request.app.state.model_settings)
    result = graph.invoke(initial_state, config=_config(thread_id))
    response = _graph_response(graph, thread_id, result)
    if response.status == "INTERRUPTED":
        _save_waiting_state(request, response.state)
    return response


@router.post("/inspections/stream")
@router.post("/api/langgraph/inspections/stream")
def stream_langgraph_inspection(
    request: Request,
    payload: LangGraphInspectionCreate,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """Stream one NDJSON event per executed LangGraph node, followed by final state."""
    graph = request.app.state.qc_langgraph
    thread_id = str(uuid4())
    initial_state = _initial_state(payload, thread_id, request.app.state.model_settings)

    def generate():
        try:
            for update in graph.stream(initial_state, config=_config(thread_id), stream_mode="updates"):
                for node, delta in update.items():
                    if node == "__interrupt__":
                        continue
                    yield json.dumps(
                        {"type": "node", "thread_id": thread_id, "node": node, "update": delta},
                        ensure_ascii=False,
                    ) + "\n"
            snapshot = graph.get_state(_config(thread_id))
            state = dict(snapshot.values)
            interrupt_value = _snapshot_interrupt(snapshot)
            status = "INTERRUPTED" if snapshot.next else "COMPLETED"
            if status == "INTERRUPTED":
                _save_waiting_state(request, state)
            yield json.dumps(
                {
                    "type": "result",
                    "thread_id": thread_id,
                    "status": status,
                    "state": state,
                    "interrupt": interrupt_value,
                },
                ensure_ascii=False,
            ) + "\n"
        except Exception as error:
            yield json.dumps({"type": "error", "message": str(error)}, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/inspections/{thread_id}/resume", response_model=LangGraphRunResponse)
@router.post("/api/langgraph/inspections/{thread_id}/resume", response_model=LangGraphRunResponse)
def resume_langgraph_inspection(
    request: Request,
    thread_id: str,
    payload: LangGraphResumeRequest,
    user: CurrentUser = Depends(get_current_user),
) -> LangGraphRunResponse:
    graph = request.app.state.qc_langgraph
    snapshot = graph.get_state(_config(thread_id))
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="LangGraph thread not found")
    if not snapshot.next:
        raise HTTPException(status_code=409, detail="LangGraph thread is not waiting for HITL")
    pending_interrupt = _snapshot_interrupt(snapshot)
    if (pending_interrupt or {}).get("type") == "supervisor_escalation_review" and user.role != "QC_SUPERVISOR":
        raise HTTPException(status_code=403, detail="Requires role: QC_SUPERVISOR")
    catalog_item = None
    if payload.defect_code:
        catalog_item = request.app.state.database.get_defect_code(payload.defect_code)
        if catalog_item is None:
            raise HTTPException(status_code=422, detail="Unknown or inactive defect code")
        graph.update_state(
            _config(thread_id),
            {
                "classified_defect_code": catalog_item["defect_code"],
                "defect_type": catalog_item["defect_type"],
                "defect_family": catalog_item.get("defect_family"),
                "catalog_defect_type": catalog_item["defect_type"],
                "severity": payload.severity or catalog_item["default_severity"],
                "severity_source_id": catalog_item.get("source_id"),
            },
        )
    try:
        result = graph.invoke(Command(resume=payload.model_dump()), config=_config(thread_id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    response = _graph_response(graph, thread_id, result)
    if response.status == "INTERRUPTED":
        _save_waiting_state(request, response.state)
    if catalog_item:
        qc_record = request.app.state.database.create_qc_decision(
            {
                "thread_id": thread_id,
                "inspection_id": response.state["inspection_id"],
                "vehicle_id": response.state["vehicle_id"],
                "defect_code": catalog_item["defect_code"],
                "defect_type": catalog_item["defect_type"],
                "location": payload.location or "unspecified_location",
                "length_mm": payload.length_mm,
                "severity": payload.severity or response.state.get("severity", "UNASSESSED"),
                "action": payload.action,
                "disposition": payload.disposition or (
                    "PASS" if payload.action == "REJECT" else "HOLD"
                ),
                "reviewer": payload.reviewer,
                "reason": payload.reason,
                "notes": payload.notes,
            }
        )
        response.state["qc_decision_record"] = qc_record
        request.app.state.qc_repository.save(response.state)
    return response


@router.get("/inspections/{thread_id}/state", response_model=LangGraphRunResponse)
@router.get("/api/langgraph/inspections/{thread_id}", response_model=LangGraphRunResponse)
def get_langgraph_inspection(request: Request, thread_id: str) -> LangGraphRunResponse:
    graph = request.app.state.qc_langgraph
    snapshot = graph.get_state(_config(thread_id))
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="LangGraph thread not found")
    interrupt_value = _snapshot_interrupt(snapshot)
    return LangGraphRunResponse(
        thread_id=thread_id,
        status="INTERRUPTED" if snapshot.next else "COMPLETED",
        state=dict(snapshot.values),
        interrupt=interrupt_value,
    )


@router.get("/agent/runs", response_model=list[LangGraphRunResponse])
@router.get("/api/agent/runs", response_model=list[LangGraphRunResponse])
def list_agent_runs(request: Request) -> list[LangGraphRunResponse]:
    return [
        LangGraphRunResponse(
            thread_id=state["thread_id"],
            status="INTERRUPTED" if state.get("final_status") == "WAITING_FOR_HITL" else "COMPLETED",
            state=state,
            interrupt=None,
        )
        for state in request.app.state.qc_repository.list_with_metadata()
    ]


@router.get("/agent/runs/export.jsonl")
@router.get("/api/agent/runs/export.jsonl")
def export_agent_runs(request: Request) -> StreamingResponse:
    """Download all persisted run audits as one portable JSONL file."""
    records = [build_audit_export(state) for state in request.app.state.qc_repository.list()]
    payload = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _attachment(
        payload.encode("utf-8"),
        filename=f"visual-qc-audit-{stamp}.jsonl",
        media_type="application/x-ndjson; charset=utf-8",
    )


@router.get("/agent/runs/{thread_id}/export.json")
@router.get("/api/agent/runs/{thread_id}/export.json")
def export_agent_run(request: Request, thread_id: str) -> StreamingResponse:
    """Download one inspection with CV, LangGraph, policy, HITL and reasoning evidence."""
    state = request.app.state.qc_repository.get(thread_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Persisted Agent run not found")
    payload = json.dumps(build_audit_export(state), ensure_ascii=False, indent=2).encode("utf-8")
    return _attachment(
        payload,
        filename=f"visual-qc-inspection-{thread_id}.json",
        media_type="application/json; charset=utf-8",
    )


@router.delete("/agent/runs")
@router.delete("/api/agent/runs")
def clear_agent_runs(
    request: Request, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Clear persisted traces and invalidate the persisted LangGraph checkpoints."""
    deleted = request.app.state.qc_repository.clear()
    conn = request.app.state.qc_checkpointer_conn
    conn.execute("DELETE FROM checkpoints")
    conn.execute("DELETE FROM writes")
    conn.commit()
    return {"deleted": deleted, "status": "CLEARED"}


@router.get("/agent/graph", response_model=AgentGraphResponse)
@router.get("/api/agent/graph", response_model=AgentGraphResponse)
def get_agent_graph(request: Request) -> AgentGraphResponse:
    mermaid = request.app.state.qc_langgraph.get_graph().draw_mermaid()
    return AgentGraphResponse(
        mermaid=mermaid,
        nodes=[
            "prepare_input",
            "detect_defect",
            "assess_result",
            "verify_defect",
            "human_review",
            "supervisor_review",
            "generate_recommendation",
            "save_result",
        ],
        checkpointer=type(request.app.state.qc_checkpointer).__name__,
    )


@router.post("/inspections/from-image", response_model=LangGraphRunResponse, status_code=201)
@router.post(
    "/api/langgraph/inspections/from-image",
    response_model=LangGraphRunResponse,
    status_code=201,
)
def run_uploaded_image_inspection(
    request: Request,
    file: UploadFile = File(...),
    vehicle_id: str = Form(...),
    vehicle_model: str = Form("unknown_model"),
    camera_id: str = Form("cam-fns-01"),
    zone_name: str = Form("unknown_zone"),
    lot_id: str | None = Form(default=None),
    shift_id: str | None = Form(default=None),
    production_date: str | None = Form(default=None),
    station_id: str = Form("FNS_LINE_HA_01"),
    user: CurrentUser = Depends(get_current_user),
) -> LangGraphRunResponse:
    """Persist the validated image to object storage and run the model-backed graph."""
    allowed_types = {"image/jpeg": ".jpg", "image/png": ".png"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Only JPEG and PNG images are accepted")
    data = file.file.read(15 * 1024 * 1024 + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds the 15 MB limit")
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            image.verify()
    except Exception as error:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image") from error

    thread_id = str(uuid4())
    inspection_id = str(uuid4())
    suffix = allowed_types[file.content_type]
    object_key = f"inspections/{inspection_id}/original{suffix}"
    request.app.state.object_storage.put(object_key, data, file.content_type)

    scratch_path = _write_scratch_image(data, suffix)
    try:
        payload = LangGraphInspectionCreate(
            inspection_id=inspection_id,
            vehicle_id=vehicle_id,
            vehicle_model=vehicle_model,
            lot_id=lot_id,
            shift_id=shift_id,
            production_date=production_date,
            station_id=station_id,
            image_url=f"/assets/objects/{object_key}",
            image_paths=[str(scratch_path)],
            camera_id=camera_id,
            zone_name=zone_name,
        )
        initial_state = _initial_state(payload, thread_id, request.app.state.model_settings)
        initial_state["image_sha256"] = hashlib.sha256(data).hexdigest()
        graph = request.app.state.qc_langgraph
        result = graph.invoke(initial_state, config=_config(thread_id))
        response = _graph_response(graph, thread_id, result)
        _attach_rendered_defect_images(
            request, response.state, inspection_id, {camera_id: scratch_path}
        )
        if response.status == "INTERRUPTED":
            _save_waiting_state(request, response.state)
        else:
            request.app.state.qc_repository.save(response.state)
        return response
    finally:
        scratch_path.unlink(missing_ok=True)


@router.post("/inspections/from-images", response_model=LangGraphRunResponse, status_code=201)
@router.post(
    "/api/langgraph/inspections/from-images",
    response_model=LangGraphRunResponse,
    status_code=201,
)
def run_uploaded_images_inspection(
    request: Request,
    files: list[UploadFile] = File(...),
    camera_ids: list[str] = Form(...),
    vehicle_id: str = Form(...),
    vehicle_model: str = Form("unknown_model"),
    zone_name: str = Form("unknown_zone"),
    lot_id: str | None = Form(default=None),
    shift_id: str | None = Form(default=None),
    production_date: str | None = Form(default=None),
    station_id: str = Form("FNS_LINE_HA_01"),
    user: CurrentUser = Depends(get_current_user),
) -> LangGraphRunResponse:
    """Run one vehicle inspection from one to five synchronized camera frames.

    Each frame remains attributable to its camera. The detector aggregates the
    results before the LangGraph policy decision; it never silently treats two
    camera observations as the same physical defect without calibration data.
    """
    allowed_types = {"image/jpeg": ".jpg", "image/png": ".png"}
    max_file_size = 15 * 1024 * 1024
    if not 1 <= len(files) <= 5:
        raise HTTPException(status_code=422, detail="Submit between 1 and 5 camera images")
    if len(files) != len(camera_ids):
        raise HTTPException(status_code=422, detail="files and camera_ids must have the same count")
    normalized_camera_ids = [camera_id.strip() for camera_id in camera_ids]
    if any(not camera_id for camera_id in normalized_camera_ids):
        raise HTTPException(status_code=422, detail="camera_ids cannot be empty")
    if len(set(normalized_camera_ids)) != len(normalized_camera_ids):
        raise HTTPException(status_code=422, detail="camera_ids must be unique per inspection")

    validated: list[tuple[UploadFile, bytes, str]] = []
    for file in files:
        suffix = allowed_types.get(file.content_type or "")
        if suffix is None:
            raise HTTPException(status_code=415, detail="Only JPEG and PNG images are accepted")
        data = file.file.read(max_file_size + 1)
        if not data:
            raise HTTPException(status_code=400, detail="Uploaded image is empty")
        if len(data) > max_file_size:
            raise HTTPException(status_code=413, detail="Each image must not exceed the 15 MB limit")
        try:
            from PIL import Image

            with Image.open(BytesIO(data)) as image:
                image.verify()
        except Exception as error:
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid image") from error
        validated.append((file, data, suffix))

    thread_id = str(uuid4())
    inspection_id = str(uuid4())
    camera_evidence: list[dict[str, str]] = []
    scratch_paths: list[Path] = []
    for index, ((file, data, suffix), camera_id) in enumerate(zip(validated, normalized_camera_ids, strict=True), start=1):
        object_key = f"inspections/{inspection_id}/camera-{index}{suffix}"
        request.app.state.object_storage.put(object_key, data, file.content_type or "application/octet-stream")
        scratch_path = _write_scratch_image(data, suffix)
        scratch_paths.append(scratch_path)
        camera_evidence.append(
            {
                "camera_id": camera_id,
                "image_url": f"/assets/objects/{object_key}",
                "image_path": str(scratch_path),
                "image_sha256": hashlib.sha256(data).hexdigest(),
            }
        )

    try:
        primary = camera_evidence[0]
        payload = LangGraphInspectionCreate(
            inspection_id=inspection_id,
            vehicle_id=vehicle_id,
            vehicle_model=vehicle_model,
            lot_id=lot_id,
            shift_id=shift_id,
            production_date=production_date,
            station_id=station_id,
            image_url=primary["image_url"],
            image_paths=[item["image_path"] for item in camera_evidence],
            camera_id=primary["camera_id"],
            zone_name=zone_name,
        )
        initial_state = _initial_state(payload, thread_id, request.app.state.model_settings)
        initial_state["image_sha256"] = primary["image_sha256"]
        initial_state["camera_evidence"] = camera_evidence
        graph = request.app.state.qc_langgraph
        result = graph.invoke(initial_state, config=_config(thread_id))
        response = _graph_response(graph, thread_id, result)
        scratch_path_by_camera = {
            item["camera_id"]: scratch_path
            for item, scratch_path in zip(camera_evidence, scratch_paths, strict=True)
        }
        _attach_rendered_defect_images(request, response.state, inspection_id, scratch_path_by_camera)
        if response.status == "INTERRUPTED":
            _save_waiting_state(request, response.state)
        else:
            request.app.state.qc_repository.save(response.state)
        return response
    finally:
        for scratch_path in scratch_paths:
            scratch_path.unlink(missing_ok=True)


@router.post("/inspections/from-videos", response_model=LangGraphRunResponse, status_code=201)
@router.post(
    "/api/langgraph/inspections/from-videos",
    response_model=LangGraphRunResponse,
    status_code=201,
)
def run_uploaded_videos_inspection(
    request: Request,
    files: list[UploadFile] = File(...),
    camera_ids: list[str] = Form(...),
    vehicle_id: str = Form(...),
    vehicle_model: str = Form("unknown_model"),
    zone_name: str = Form("unknown_zone"),
    lot_id: str | None = Form(default=None),
    shift_id: str | None = Form(default=None),
    production_date: str | None = Form(default=None),
    station_id: str = Form("FNS_LINE_HA_01"),
    frame_interval: float = Form(default=1.0),
    user: CurrentUser = Depends(get_current_user),
) -> LangGraphRunResponse:
    """Run one vehicle inspection from 1-5 video files (one per camera).

    Extracts frames from each video at specified interval, deduplicates detections
    per camera (Tier-1), then aggregates across cameras (Tier-2) before LangGraph processing.
    """
    max_file_size = 500 * 1024 * 1024
    if not 1 <= len(files) <= 5:
        raise HTTPException(status_code=422, detail="Submit between 1 and 5 camera videos")
    if len(files) != len(camera_ids):
        raise HTTPException(status_code=422, detail="files and camera_ids must have the same count")

    normalized_camera_ids = [camera_id.strip() for camera_id in camera_ids]
    if any(not camera_id for camera_id in normalized_camera_ids):
        raise HTTPException(status_code=422, detail="camera_ids cannot be empty")
    if len(set(normalized_camera_ids)) != len(normalized_camera_ids):
        raise HTTPException(status_code=422, detail="camera_ids must be unique per inspection")

    try:
        frame_interval = float(frame_interval)
        if not (0.5 <= frame_interval <= 2.0):
            raise ValueError("frame_interval must be between 0.5 and 2.0 seconds")
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid frame_interval: {str(e)}")

    validated_videos: list[tuple[str, bytes]] = []
    for file in files:
        if not VideoProcessor.is_valid_video_format(file.filename or "", file.content_type):
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported video format: {file.filename}. Supported: MP4, MOV, WebM, AVI, MKV, FLV",
            )

        data = file.file.read(max_file_size + 1)
        if not data:
            raise HTTPException(status_code=400, detail=f"Video file is empty: {file.filename}")
        if len(data) > max_file_size:
            raise HTTPException(
                status_code=413, detail=f"Video {file.filename} exceeds 500 MB limit"
            )

        validated_videos.append((file.filename or "video", data))

    thread_id = str(uuid4())
    inspection_id = str(uuid4())

    temp_video_paths: list[Path] = []
    try:
        temp_dir = Path(tempfile.gettempdir()) / f"qc_videos_{inspection_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        video_processor = VideoProcessor(extract_interval=frame_interval, temp_dir=str(temp_dir))

        camera_evidence: list[dict[str, str]] = []
        scratch_paths_by_camera: dict[str, Path] = {}

        for (filename, video_data), camera_id in zip(validated_videos, normalized_camera_ids):
            temp_video_path = temp_dir / f"{camera_id}.mp4"
            temp_video_path.write_bytes(video_data)
            temp_video_paths.append(temp_video_path)

            try:
                extraction_result = video_processor.extract_frames(
                    temp_video_path,
                    camera_id=camera_id,
                    model_image_size=request.app.state.model_settings.model_image_size,
                )

                logger.info(
                    f"Video: {camera_id} - extracted {extraction_result['extracted_frame_count']} frames "
                    f"from {extraction_result['frame_count']} (duration: {extraction_result['duration_seconds']}s)"
                )

                video_key = f"inspections/{inspection_id}/videos/{camera_id}.mp4"
                request.app.state.object_storage.put(video_key, video_data, "video/mp4")

                frame_dir = temp_dir / camera_id
                frame_dir.mkdir(parents=True, exist_ok=True)

                for i, frame_info in enumerate(extraction_result["frames"]):
                    import cv2

                    frame_path = frame_dir / f"frame_{i:03d}_{frame_info['timestamp']:.2f}s.jpg"
                    cv2.imwrite(str(frame_path), frame_info["frame_data"])

                if extraction_result["frames"]:
                    import cv2

                    first_frame = cv2.imread(str(frame_dir / "frame_000_0.00s.jpg"))
                    if first_frame is not None:
                        _, first_frame_jpg = cv2.imencode(".jpg", first_frame)
                        first_frame_data = first_frame_jpg.tobytes()
                        image_key = f"inspections/{inspection_id}/camera-{camera_id}-frame0.jpg"
                        request.app.state.object_storage.put(
                            image_key, first_frame_data, "image/jpeg"
                        )

                        scratch_path = _write_scratch_image(first_frame_data, ".jpg")
                        scratch_paths_by_camera[camera_id] = scratch_path

                        camera_evidence.append(
                            {
                                "camera_id": camera_id,
                                "image_url": f"/assets/objects/{image_key}",
                                "image_path": str(scratch_path),
                                "image_sha256": hashlib.sha256(first_frame_data).hexdigest(),
                                "video_source": True,
                                "source_frames": extraction_result["extracted_frame_count"],
                            }
                        )

            except VideoProcessingError as e:
                raise HTTPException(status_code=422, detail=f"Video error ({camera_id}): {str(e)}")
            except Exception as e:
                logger.exception(f"Error processing video {camera_id}")
                raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")

        if not camera_evidence:
            raise HTTPException(status_code=422, detail="No valid frames extracted from videos")

        primary = camera_evidence[0]
        payload = LangGraphInspectionCreate(
            inspection_id=inspection_id,
            vehicle_id=vehicle_id,
            vehicle_model=vehicle_model,
            lot_id=lot_id,
            shift_id=shift_id,
            production_date=production_date,
            station_id=station_id,
            image_url=primary["image_url"],
            image_paths=[item["image_path"] for item in camera_evidence],
            camera_id=primary["camera_id"],
            zone_name=zone_name,
        )

        initial_state = _initial_state(payload, thread_id, request.app.state.model_settings)
        initial_state["image_sha256"] = primary["image_sha256"]
        initial_state["camera_evidence"] = camera_evidence
        initial_state["video_source"] = True

        graph = request.app.state.qc_langgraph
        result = graph.invoke(initial_state, config=_config(thread_id))
        response = _graph_response(graph, thread_id, result)

        _attach_rendered_defect_images(request, response.state, inspection_id, scratch_paths_by_camera)

        if response.status == "INTERRUPTED":
            _save_waiting_state(request, response.state)
        else:
            request.app.state.qc_repository.save(response.state)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in video inspection")
        raise HTTPException(status_code=500, detail=f"Video inspection failed: {str(e)}")
    finally:
        for path in temp_video_paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

        for scratch_path in scratch_paths_by_camera.values():
            try:
                scratch_path.unlink(missing_ok=True)
            except Exception:
                pass
