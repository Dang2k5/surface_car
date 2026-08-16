from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.graph.builder import build_qc_graph
from agent.graph.state import QCState
from agent.services.audit_export import build_audit_export

from .langgraph_schemas import (
    AgentGraphResponse,
    LangGraphInspectionCreate,
    LangGraphResumeRequest,
    LangGraphRunResponse,
)

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
    is_mock = settings.detector_provider == "mock"
    state: QCState = {
        "thread_id": thread_id,
        "inspection_id": payload.inspection_id or str(uuid4()),
        "vehicle_id": payload.vehicle_id,
        "vehicle_model": payload.vehicle_model,
        "image_url": payload.image_url or "",
        "image_paths": payload.image_paths,
        "camera_id": payload.camera_id,
        "zone_name": payload.zone_name,
        "verify_count": 0,
        "retry_count": 0,
        "max_retries": 2,
        "auto_pass_enabled": True if is_mock else settings.auto_pass_enabled,
        "confirmed_threshold": 0.85 if is_mock else settings.confirmed_threshold,
        "verify_threshold": 0.50 if is_mock else settings.verify_threshold,
        "execution_trace": [],
    }
    if is_mock:
        marker = (payload.image_url or "").lower()
        scenarios = (
            "no_defect",
            "high_confidence",
            "medium_confirmed",
            "verify_uncertain",
            "low_confidence",
            "unknown_defect",
        )
        state["mock_scenario"] = next(
            (scenario for scenario in scenarios if scenario in marker),
            "high_confidence",
        )
    return state


def _save_waiting_state(request: Request, state: dict[str, Any]) -> None:
    request.app.state.qc_repository.save({**state, "final_status": "WAITING_FOR_HITL"})


@router.post("/inspections", response_model=LangGraphRunResponse, status_code=201)
@router.post("/api/langgraph/inspections", response_model=LangGraphRunResponse, status_code=201)
def run_langgraph_inspection(
    request: Request,
    payload: LangGraphInspectionCreate,
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
def stream_langgraph_inspection(request: Request, payload: LangGraphInspectionCreate) -> StreamingResponse:
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
) -> LangGraphRunResponse:
    graph = request.app.state.qc_langgraph
    snapshot = graph.get_state(_config(thread_id))
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="LangGraph thread not found")
    if not snapshot.next:
        raise HTTPException(status_code=409, detail="LangGraph thread is not waiting for HITL")
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
                "severity": payload.severity or catalog_item["default_severity"],
            },
        )
    result = graph.invoke(Command(resume=payload.model_dump()), config=_config(thread_id))
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
                    "REINSPECT" if payload.action == "REJECT" else "HOLD"
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
        for state in request.app.state.qc_repository.list()
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
def clear_agent_runs(request: Request) -> dict[str, Any]:
    """Clear persisted traces and invalidate in-memory HITL checkpoints."""
    deleted = request.app.state.qc_repository.clear()
    request.app.state.qc_checkpointer = InMemorySaver()
    request.app.state.qc_langgraph = build_qc_graph(
        detector=request.app.state.qc_detector,
        verifier=request.app.state.qc_verifier,
        reasoning=request.app.state.qc_reasoning,
        policy_catalog=request.app.state.qc_policy_catalog,
        repository=request.app.state.qc_repository,
        checkpointer=request.app.state.qc_checkpointer,
        defect_catalog=request.app.state.qc_defect_catalog,
    )
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
) -> LangGraphRunResponse:
    """Persist a validated image locally and run the configured model-backed graph."""
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
    relative_path = Path(inspection_id) / f"original{suffix}"
    upload_root = Path(__file__).resolve().parents[2] / "data" / "uploads"
    destination = upload_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    payload = LangGraphInspectionCreate(
        inspection_id=inspection_id,
        vehicle_id=vehicle_id,
        vehicle_model=vehicle_model,
        image_url=f"/assets/uploads/{relative_path.as_posix()}",
        image_paths=[str(destination)],
        camera_id=camera_id,
        zone_name=zone_name,
    )
    initial_state = _initial_state(payload, thread_id, request.app.state.model_settings)
    initial_state["image_sha256"] = hashlib.sha256(data).hexdigest()
    graph = request.app.state.qc_langgraph
    result = graph.invoke(initial_state, config=_config(thread_id))
    response = _graph_response(graph, thread_id, result)
    if response.status == "INTERRUPTED":
        _save_waiting_state(request, response.state)
    return response


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
    upload_root = Path(__file__).resolve().parents[2] / "data" / "uploads"
    camera_evidence: list[dict[str, str]] = []
    for index, ((_, data, suffix), camera_id) in enumerate(zip(validated, normalized_camera_ids, strict=True), start=1):
        relative_path = Path(inspection_id) / f"camera-{index}{suffix}"
        destination = upload_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        camera_evidence.append(
            {
                "camera_id": camera_id,
                "image_url": f"/assets/uploads/{relative_path.as_posix()}",
                "image_path": str(destination),
                "image_sha256": hashlib.sha256(data).hexdigest(),
            }
        )

    primary = camera_evidence[0]
    payload = LangGraphInspectionCreate(
        inspection_id=inspection_id,
        vehicle_id=vehicle_id,
        vehicle_model=vehicle_model,
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
    if response.status == "INTERRUPTED":
        _save_waiting_state(request, response.state)
    return response
