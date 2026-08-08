from __future__ import annotations

from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.graph.builder import build_qc_graph
from agent.services.repository import MockQCRepository

IMAGE_URL = "/assets/train/21_PNG.rf.cc6bbeaaba838656af9d4945bddc1129.jpg"


def run_scenario(scenario: str):
    repository = MockQCRepository()
    graph = build_qc_graph(repository=repository, checkpointer=InMemorySaver())
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        {
            "thread_id": thread_id,
            "inspection_id": str(uuid4()),
            "vehicle_id": f"TEST-{scenario}",
            "image_url": IMAGE_URL,
            "image_paths": [],
            "camera_id": "cam-test",
            "panel": "door_panel",
            "mock_scenario": scenario,
            "execution_trace": [],
        },
        config=config,
    )
    return graph, repository, thread_id, config, result


def test_no_defect_routes_to_pass_and_save():
    _, repository, thread_id, _, result = run_scenario("no_defect")
    assert result["decision"] == "PASS"
    assert result["recommendation_code"] == "RELEASE_TO_NEXT_QUALITY_GATE"
    assert result["recommendation"] == "Release the vehicle to the next quality gate"
    assert result["final_status"] == "PASS"
    assert repository.get(thread_id)["final_status"] == "PASS"


def test_high_confidence_defect_generates_recommendation():
    _, repository, thread_id, _, result = run_scenario("high_confidence")
    assert result["decision"] == "DEFECT_CONFIRMED"
    assert result["verify_count"] == 0
    assert result["recommendation_code"] == "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT"
    assert result["recommendation"] == "Hold the vehicle and transfer it to Body Repair for technical assessment"
    assert "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT" not in result["reason"]
    assert repository.get(thread_id)["final_status"] == "HOLD_FOR_REWORK"


def test_medium_confidence_verifies_once_then_confirms():
    _, _, _, _, result = run_scenario("medium_confirmed")
    assert result["verify_count"] == 1
    assert result["verify_result"] == "CONFIRMED"
    assert result["recommendation_code"] == "SURFACE_POLISH_AND_REINSPECT"
    assert result["recommendation"] == "Polish the affected surface and perform a documented reinspection"
    trace_nodes = [event["node"] for event in result["execution_trace"]]
    assert trace_nodes.count("verify_defect") == 1
    assert trace_nodes.count("assess_result") == 2


def test_uncertain_verification_interrupts_and_resumes_hitl():
    graph, repository, thread_id, config, result = run_scenario("verify_uncertain")
    assert result["verify_count"] == 2
    assert result["human_required"] is True
    assert result["__interrupt__"][0].value["type"] == "visual_qc_review"
    assert repository.get(thread_id) is None

    resumed = graph.invoke(
        Command(
            resume={
                "action": "APPROVE",
                "reviewer": "qc-test",
                "reason": "Defect confirmed during manual inspection.",
            }
        ),
        config=config,
    )
    assert resumed["human_decision"]["action"] == "APPROVE"
    assert resumed["recommendation_code"] == "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT"
    assert resumed["recommendation"] == "Hold the vehicle and transfer it to Body Repair for technical assessment"
    assert repository.get(thread_id)["final_status"] == "HOLD_FOR_REWORK"
