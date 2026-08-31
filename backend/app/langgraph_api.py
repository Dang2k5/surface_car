from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
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
    VideoProcessingError,
)
from agent.services.yolo_detector import _group_findings, detection_priority_key

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


def _apply_operator_classification(
    item: dict[str, Any], catalog_item: dict[str, Any]
) -> dict[str, Any]:
    """Fold an operator's HITL defect_code choice into one previously-unresolved
    camera_classifications entry, mirroring what _classify_local_detection (agent/graph/
    nodes.py) would have set had the catalog/LLM matched it automatically -- including
    the classification_rule the operator's code carries, since a manually-picked code
    isn't guaranteed to already be in this detection's own suggested_defect_codes list."""
    suggested = list(item.get("suggested_defect_codes") or [])
    if not any(c.get("defect_code") == catalog_item["defect_code"] for c in suggested):
        suggested.append(catalog_item)
    return {
        **item,
        "suggested_defect_codes": suggested,
        "classified_defect_code": catalog_item["defect_code"],
        "defect_family": catalog_item.get("defect_family"),
        "catalog_defect_type": catalog_item["defect_type"],
        "severity": catalog_item["default_severity"],
        "severity_source_id": catalog_item.get("source_id"),
    }


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


def _submitter_name(user: CurrentUser) -> str:
    """The person who ran this inspection (supervisor's "Người thực hiện" column) — never
    the HITL reviewer, which is a separate, later, and often-absent field."""
    return user.full_name or user.email or user.user_id


def _enforce_line_gate(request: Request, station_id: str) -> bool:
    """Andon-style line control, checked once at the top of every inspection-submitting
    endpoint (docs discussion: HITL rate response ladder).

    - STOPPED (a QC_SUPERVISOR explicitly stopped this station via
      backend/app/hitl_alerts_api.py) rejects the submission outright with 423 — this is the
      ONLY place a human decision (never an automatic threshold) blocks new inspections.
    - CRITICAL HITL rate (computed live, never persisted — see HitlRateAlertService) does NOT
      block anything; it returns True so the caller sets QCState.force_human_review, which
      routes every new inspection through human_review instead of letting it auto-PASS/CONFIRM
      silently (agent/graph/nodes.py's assess_result).

    Returns whether this station's new inspection must be forced through human_review.
    """
    line_status = request.app.state.database.get_line_status(station_id)
    if line_status is not None and line_status.get("status") == "STOPPED":
        raise HTTPException(
            status_code=423,
            detail={
                "code": "LINE_STOPPED",
                "message_vi": (
                    f"Trạm {station_id} đang tạm dừng: {line_status.get('stop_reason') or 'không rõ lý do'}. "
                    "Liên hệ QC Supervisor để tiếp tục."
                ),
                "stopped_by": line_status.get("stopped_by"),
                "stopped_at": line_status.get("stopped_at"),
            },
        )
    alert = request.app.state.hitl_alert_service.analyze(station_id=station_id)
    return bool(alert and alert.severity == "CRITICAL")


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
    scratch_path_by_detection: dict[str, Path] | None = None,
) -> None:
    """Render overlay/crop/mask PNGs for every detection (not just the primary one) and store
    them in object storage (FR-17, API_CONTRACT.md), so a secondary-camera finding gets its own
    real crop instead of the UI falling back to that camera's uncropped full photo. Skips a
    detection when there is nothing to render for it, and never fails the inspection response
    if rendering one detection fails — the rest still get rendered.

    `scratch_path_by_detection` (video inspections only, see _track_camera_across_frames) takes
    priority per-detection: a camera can have several merged defects each observed in a
    different extracted frame, so falling back to the single camera-wide representative frame
    for every one of them would crop the wrong image for any defect not observed in that frame."""
    primary_detection_id = state.get("primary_detection_id")
    enriched_by_id = {
        item.get("detection_id"): item for item in state.get("enriched_defects") or []
    }
    for detection in state.get("detections") or []:
        detection_id = detection.get("detection_id")
        scratch_path = (scratch_path_by_detection or {}).get(detection_id) or scratch_path_by_camera.get(
            str(detection.get("camera_id"))
        )
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
    force_human_review = _enforce_line_gate(request, payload.station_id)
    graph = request.app.state.qc_langgraph
    thread_id = str(uuid4())
    initial_state = _initial_state(payload, thread_id, request.app.state.model_settings)
    initial_state["force_human_review"] = force_human_review
    initial_state["submitted_by"] = _submitter_name(user)
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
    camera_classifications = snapshot.values.get("camera_classifications") or []
    unresolved_ids = {
        item["detection_id"] for item in camera_classifications if item.get("classified_defect_code") is None
    }
    catalog_item = None
    state_update = None
    if payload.detection_resolutions:
        resolved_ids = {resolution.detection_id for resolution in payload.detection_resolutions}
        if resolved_ids != unresolved_ids:
            raise HTTPException(
                status_code=422,
                detail=(
                    "detection_resolutions must cover exactly the unresolved findings "
                    f"(expected {sorted(unresolved_ids)}, got {sorted(resolved_ids)})"
                ),
            )
        catalog_item_by_detection: dict[str, dict[str, Any]] = {}
        for resolution in payload.detection_resolutions:
            found = request.app.state.database.get_defect_code(resolution.defect_code)
            if found is None:
                raise HTTPException(
                    status_code=422, detail=f"Unknown or inactive defect code: {resolution.defect_code}"
                )
            catalog_item_by_detection[resolution.detection_id] = found
        # A single top-level classified_defect_code/severity still drives the vehicle's own
        # audit-record verdict (qc_decision_record below) and Kết luận card -- worst-wins,
        # same convention QCNodes.detect_defect already uses to pick one decision among
        # several independent findings.
        worst_item = max(
            (item for item in camera_classifications if item["detection_id"] in catalog_item_by_detection),
            key=detection_priority_key,
        )
        catalog_item = catalog_item_by_detection[worst_item["detection_id"]]
        state_update = {
            "classified_defect_code": catalog_item["defect_code"],
            "defect_type": catalog_item["defect_type"],
            "defect_family": catalog_item.get("defect_family"),
            "catalog_defect_type": catalog_item["defect_type"],
            "severity": payload.severity or catalog_item["default_severity"],
            "severity_source_id": catalog_item.get("source_id"),
            "camera_classifications": [
                _apply_operator_classification(item, catalog_item_by_detection[item["detection_id"]])
                if item["detection_id"] in catalog_item_by_detection
                else item
                for item in camera_classifications
            ],
        }
    elif payload.defect_code:
        if len(unresolved_ids) > 1:
            raise HTTPException(
                status_code=422,
                detail=(
                    "This case has multiple unresolved findings -- use detection_resolutions "
                    "(one defect_code per detection_id) instead of the single defect_code field"
                ),
            )
        catalog_item = request.app.state.database.get_defect_code(payload.defect_code)
        if catalog_item is None:
            raise HTTPException(status_code=422, detail="Unknown or inactive defect code")
        state_update = {
            "classified_defect_code": catalog_item["defect_code"],
            "defect_type": catalog_item["defect_type"],
            "defect_family": catalog_item.get("defect_family"),
            "catalog_defect_type": catalog_item["defect_type"],
            "severity": payload.severity or catalog_item["default_severity"],
            "severity_source_id": catalog_item.get("source_id"),
            # detect_defect (agent/graph/nodes.py) only ever leaves classified_defect_code
            # unset on a per-detection camera_classifications entry when it required HITL
            # (unresolved_camera_ids / LLM unavailable). The top-level fields above resolve
            # the vehicle's own verdict, but the frontend's per-finding "Ngưỡng" card
            # (frontend/src/lib/detection-geometry.ts's thresholdFor) reads the *per-detection*
            # classified_defect_code -- without also patching these entries here, that field
            # stays permanently null after the operator resolves it, showing "—" forever even
            # though Mức độ/Kết luận already reflect the operator's decision correctly.
            "camera_classifications": [
                _apply_operator_classification(item, catalog_item)
                if item.get("classified_defect_code") is None
                else item
                for item in camera_classifications
            ],
        }
    try:
        # Command carries the defect_code state update alongside the resume value so this
        # only writes one checkpoint round-trip to the (remote) Postgres checkpointer instead
        # of two sequential ones (a separate graph.update_state() call followed by invoke()) --
        # that extra round-trip was adding noticeable latency to every resume that includes a
        # defect_code, which is effectively every APPROVE/OVERRIDE submission.
        result = graph.invoke(
            Command(resume=payload.model_dump(), update=state_update),
            config=_config(thread_id),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    response = _graph_response(graph, thread_id, result)
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
    # Persist exactly once: an INTERRUPTED response (e.g. an operator's OVERRIDE now waiting
    # on supervisor_review) must keep the "WAITING_FOR_HITL" final_status marker that
    # list_agent_runs relies on to report status=INTERRUPTED -- a second unconditional save
    # here (after _save_waiting_state) used to overwrite it back to unset, making the case
    # silently report as COMPLETED and vanish from the supervisor's escalation queue.
    if response.status == "INTERRUPTED":
        _save_waiting_state(request, response.state)
    elif catalog_item:
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
    force_human_review = _enforce_line_gate(request, station_id)
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
        initial_state["force_human_review"] = force_human_review
        initial_state["submitted_by"] = _submitter_name(user)
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
    force_human_review = _enforce_line_gate(request, station_id)
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
        initial_state["force_human_review"] = force_human_review
        initial_state["submitted_by"] = _submitter_name(user)
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


def _track_camera_across_frames(
    detector: Any, camera_id: str, frames: list[dict[str, Any]]
) -> dict[str, Any]:
    """Run detection on every frame extracted from one camera's video and merge repeated
    observations of the same physical defect across frames (DefectDeduplicator's Tier-1
    spatial+temporal merge), so a scratch visible for several seconds is tracked as ONE
    defect instead of counted once per frame it happens to appear in.

    `frames`: [{"timestamp": float, "image_path": str}, ...], in extraction order.
    All of this camera's frames are sent to the detector in a SINGLE batched detect() call
    (like the multi-camera photo upload already does) instead of one call per frame --
    detect() returns camera_results in the same order as the submitted evidence list, so
    the i-th result maps directly back to frames[i].

    Returns a dict with the merged `unique_defects` plus the representative frame (the one
    the highest-priority merged defect was actually observed in) whose image should be
    shown/stored for this camera, so the % bounding box the frontend draws stays aligned
    with the photo it is drawn over.
    """
    frame_state: dict[str, Any] = {
        "camera_evidence": [
            {"camera_id": camera_id, "image_url": "", "image_path": frame["image_path"]}
            for frame in frames
        ]
    }
    result = detector.detect(frame_state)
    camera_results = result["camera_results"]

    detections_by_frame: list[dict[str, Any]] = []
    frame_meta: dict[float, dict[str, Any]] = {}
    model_meta: dict[str, Any] = {
        "model_name": result.get("model_name"),
        "model_version": result.get("model_version"),
        "model_task": result.get("model_task"),
    }

    for frame_index, (frame, camera_result) in enumerate(zip(frames, camera_results, strict=True)):
        # Each per-frame result restarts detection_id numbering from 0 (e.g. "CAM-01_0"),
        # so two different frames' detections would collide once flattened together for
        # merging -- prefix with the frame index to keep every raw observation's id unique.
        frame_detections = []
        for detection in camera_result["detections"]:
            detection = dict(detection)
            local_index = detection["detection_id"].rsplit("_", 1)[-1]
            detection["detection_id"] = f"{camera_id}_f{frame_index}_{local_index}"
            frame_detections.append(detection)
        detections_by_frame.append({"timestamp": frame["timestamp"], "detections": frame_detections})
        frame_meta[frame["timestamp"]] = {
            "image_width": camera_result["image_width"],
            "image_height": camera_result["image_height"],
            "frame": frame,
        }

    total_inference_ms = float(result.get("inference_ms") or 0.0)

    merged = DefectDeduplicator().deduplicate_camera_detections(camera_id, detections_by_frame)
    unique_defects = merged["unique_defects"]

    representative_ts = frames[0]["timestamp"]
    if unique_defects:
        best = max(unique_defects, key=detection_priority_key)
        candidate_ts = best.get("_frame_timestamp")
        if candidate_ts in frame_meta:
            representative_ts = candidate_ts

    # Merge bookkeeping keys are private (leading "_") except _frame_timestamps/_track_frames,
    # which the frontend needs to know exactly when (in video-playback time) this tracked
    # defect was actually observed -- and at what exact position in each of those frames --
    # so it can show the box near the video's current time instead of burning one fixed
    # position onto the whole clip -- keep those under public names.
    clean_defects = [
        {
            **{key: value for key, value in defect.items() if not key.startswith("_")},
            "track_timestamps": sorted(defect.get("_frame_timestamps") or [defect.get("_frame_timestamp", 0.0)]),
            "track_frames": defect.get("_track_frames") or [],
        }
        for defect in unique_defects
    ]

    # A camera can have several *different* merged defects, each actually observed (and its
    # bbox measured) in a different extracted frame -- only ONE frame becomes this camera's
    # displayed evidence photo (`representative_frame` below), but cropping every defect
    # against that single frame is wrong for any defect whose own bbox came from a different
    # frame (image_render.py's render_defect_images crops THAT image at THIS bbox, so a
    # mismatched frame either crops the wrong region or a visually different moment).
    # Keep each defect's own source frame path so the caller can render its crop/overlay/mask
    # from the frame it was actually detected in.
    frame_path_by_detection_id = {
        defect.get("detection_id"): frame_meta[defect["_frame_timestamp"]]["frame"]["image_path"]
        for defect in unique_defects
        if defect.get("detection_id") and defect.get("_frame_timestamp") in frame_meta
    }

    representative = frame_meta[representative_ts]
    return {
        "camera_id": camera_id,
        "representative_frame": representative["frame"],
        "image_width": representative["image_width"],
        "image_height": representative["image_height"],
        "unique_defects": clean_defects,
        "frame_path_by_detection_id": frame_path_by_detection_id,
        "merge_info": merged["merge_info"],
        "tracked_frame_count": len(frames),
        "inference_ms": total_inference_ms,
        **model_meta,
    }


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
    frame_interval: float = Form(default=0.75),
    user: CurrentUser = Depends(get_current_user),
) -> LangGraphRunResponse:
    """Run one vehicle inspection from 1-5 video files (one per camera).

    Extracts frames from each video every `frame_interval` seconds (0.5-1s), runs detection
    on EVERY extracted frame per camera, and merges repeated observations of the same
    physical defect across frames (Tier-1, DefectDeduplicator's spatial+temporal merge) so a
    defect visible for several seconds is tracked as one finding, not one per frame. The
    frame each surviving defect was actually observed in becomes that camera's evidence
    photo, then the merged, multi-frame-tracked result feeds the normal LangGraph pipeline
    exactly like a photo upload (see QCNodes.detect_defect's `precomputed_detection`).
    """
    force_human_review = _enforce_line_gate(request, station_id)
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
        if not (0.5 <= frame_interval <= 1.0):
            raise ValueError("frame_interval must be between 0.5 and 1.0 seconds")
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

    temp_dir = Path(tempfile.gettempdir()) / f"qc_videos_{inspection_id}"
    scratch_paths_by_camera: dict[str, Path] = {}
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)

        video_processor = VideoProcessor(extract_interval=frame_interval, temp_dir=str(temp_dir))
        detector = request.app.state.qc_detector

        camera_tracks: list[dict[str, Any]] = []
        video_url_by_camera: dict[str, str] = {}

        for (filename, video_data), camera_id in zip(validated_videos, normalized_camera_ids):
            temp_video_path = temp_dir / f"{camera_id}.mp4"
            temp_video_path.write_bytes(video_data)

            try:
                extraction_result = video_processor.extract_frames(
                    temp_video_path,
                    camera_id=camera_id,
                )

                logger.info(
                    f"Video: {camera_id} - extracted {extraction_result['extracted_frame_count']} frames "
                    f"from {extraction_result['frame_count']} (duration: {extraction_result['duration_seconds']}s)"
                )

                video_key = f"inspections/{inspection_id}/videos/{camera_id}.mp4"
                request.app.state.object_storage.put(video_key, video_data, "video/mp4")
                video_url_by_camera[camera_id] = f"/assets/objects/{video_key}"

                frame_dir = temp_dir / camera_id
                frame_dir.mkdir(parents=True, exist_ok=True)

                import cv2

                frames: list[dict[str, Any]] = []
                for i, frame_info in enumerate(extraction_result["frames"]):
                    frame_path = frame_dir / f"frame_{i:03d}_{frame_info['timestamp']:.2f}s.jpg"
                    cv2.imwrite(str(frame_path), frame_info["frame_data"])
                    frames.append({"timestamp": frame_info["timestamp"], "image_path": str(frame_path)})

                if not frames:
                    continue

                camera_tracks.append(_track_camera_across_frames(detector, camera_id, frames))

            except VideoProcessingError as e:
                raise HTTPException(status_code=422, detail=f"Video error ({camera_id}): {str(e)}")
            except Exception as e:
                logger.exception(f"Error processing video {camera_id}")
                raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")

        if not camera_tracks:
            raise HTTPException(status_code=422, detail="No valid frames extracted from videos")

        camera_evidence: list[dict[str, str]] = []
        camera_results: list[dict[str, Any]] = []
        all_detections: list[dict[str, Any]] = []
        scratch_path_by_detection: dict[str, Path] = {}
        total_inference_ms = 0.0
        model_meta: dict[str, Any] = {}

        for track in camera_tracks:
            camera_id = track["camera_id"]
            frame_data = Path(track["representative_frame"]["image_path"]).read_bytes()
            image_key = f"inspections/{inspection_id}/camera-{camera_id}-frame.jpg"
            request.app.state.object_storage.put(image_key, frame_data, "image/jpeg")
            image_url = f"/assets/objects/{image_key}"

            scratch_path = _write_scratch_image(frame_data, ".jpg")
            scratch_paths_by_camera[camera_id] = scratch_path

            camera_evidence.append(
                {
                    "camera_id": camera_id,
                    "image_url": image_url,
                    "image_path": str(scratch_path),
                    "image_sha256": hashlib.sha256(frame_data).hexdigest(),
                    "video_source": True,
                    "video_url": video_url_by_camera.get(camera_id, ""),
                    "source_frames": track["tracked_frame_count"],
                }
            )
            camera_results.append(
                {
                    "camera_id": camera_id,
                    "image_url": image_url,
                    "video_url": video_url_by_camera.get(camera_id, ""),
                    "image_width": track["image_width"],
                    "image_height": track["image_height"],
                    "defect_detected": bool(track["unique_defects"]),
                    "detections": track["unique_defects"],
                    "frame_tracking": {
                        "tracked_frame_count": track["tracked_frame_count"],
                        "frame_interval_seconds": frame_interval,
                        "merge_info": track["merge_info"],
                    },
                }
            )
            all_detections.extend(track["unique_defects"])
            for detection_id, frame_path in track.get("frame_path_by_detection_id", {}).items():
                scratch_path_by_detection[detection_id] = Path(frame_path)
            total_inference_ms += track["inference_ms"]
            if not model_meta:
                model_meta = {
                    "model_name": track.get("model_name"),
                    "model_version": track.get("model_version"),
                    "model_task": track.get("model_task"),
                }

        primary_defect = max(all_detections, key=detection_priority_key, default=None)
        primary_camera = next(
            (
                camera
                for camera in camera_results
                if primary_defect and camera["camera_id"] == primary_defect["camera_id"]
            ),
            camera_results[0],
        )
        precomputed_detection: dict[str, Any] = {
            "detections": all_detections,
            "camera_results": camera_results,
            "finding_groups": _group_findings(all_detections),
            "camera_id": primary_camera["camera_id"],
            "primary_detection_id": primary_defect["detection_id"] if primary_defect else None,
            "image_width": primary_camera["image_width"],
            "image_height": primary_camera["image_height"],
            "inference_ms": round(total_inference_ms, 1),
            "inference_status": "SUCCESS",
            "defect_detected": bool(primary_defect),
            "defect_type": primary_defect["class_name"] if primary_defect else "none",
            "raw_class_name": primary_defect["raw_class_name"] if primary_defect else None,
            "confidence": primary_defect["confidence"] if primary_defect else 0.0,
            "bbox": primary_defect["bbox"] if primary_defect else None,
            "segmentation_result": primary_defect["segmentation"] if primary_defect else None,
            "visual_measurements": primary_defect["visual_measurements"] if primary_defect else {},
            "severity": "UNASSESSED",
            **model_meta,
        }

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
        initial_state["precomputed_detection"] = precomputed_detection
        initial_state["force_human_review"] = force_human_review
        initial_state["submitted_by"] = _submitter_name(user)

        graph = request.app.state.qc_langgraph
        result = graph.invoke(initial_state, config=_config(thread_id))
        response = _graph_response(graph, thread_id, result)

        _attach_rendered_defect_images(
            request,
            response.state,
            inspection_id,
            scratch_paths_by_camera,
            scratch_path_by_detection=scratch_path_by_detection,
        )

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
        shutil.rmtree(temp_dir, ignore_errors=True)
        for scratch_path in scratch_paths_by_camera.values():
            try:
                scratch_path.unlink(missing_ok=True)
            except Exception:
                pass
