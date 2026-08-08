from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
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


def _initial_state(payload: LangGraphInspectionCreate, thread_id: str) -> QCState:
    return {
        "thread_id": thread_id,
        "inspection_id": payload.inspection_id or str(uuid4()),
        "vehicle_id": payload.vehicle_id,
        "image_url": payload.image_url or "",
        "image_paths": payload.image_paths,
        "camera_id": payload.camera_id,
        "panel": payload.panel,
        "mock_scenario": payload.mock_scenario,
        "mock_detection": payload.mock_detection or {},
        "verify_count": 0,
        "retry_count": 0,
        "max_retries": 2,
        "execution_trace": [],
    }


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
    initial_state = _initial_state(payload, thread_id)
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
    initial_state = _initial_state(payload, thread_id)

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
