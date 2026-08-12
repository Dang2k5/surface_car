from __future__ import annotations

import hashlib
import json
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

from .langgraph_schemas import (
    AgentGraphResponse,
    LangGraphInspectionCreate,
    LangGraphResumeRequest,
    LangGraphRunResponse,
)

router = APIRouter(tags=["LangGraph Visual QC"])


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
        "panel": payload.panel,
        "material": payload.material,
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
    result = graph.invoke(Command(resume=payload.model_dump()), config=_config(thread_id))
    return _graph_response(graph, thread_id, result)


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
    panel: str = Form("unknown_panel"),
    material: str = Form("unknown_material"),
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
        panel=panel,
        material=material,
    )
    initial_state = _initial_state(payload, thread_id, request.app.state.model_settings)
    initial_state["image_sha256"] = hashlib.sha256(data).hexdigest()
    graph = request.app.state.qc_langgraph
    result = graph.invoke(initial_state, config=_config(thread_id))
    response = _graph_response(graph, thread_id, result)
    if response.status == "INTERRUPTED":
        _save_waiting_state(request, response.state)
    return response
