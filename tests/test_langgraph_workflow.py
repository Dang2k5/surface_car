from __future__ import annotations

from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.graph.builder import build_qc_graph
from agent.services.repository import MockQCRepository

IMAGE_URL = "/test-fixtures/inspection.jpg"


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
            "vehicle_model": "SUV_EV_2026",
            "image_url": IMAGE_URL,
            "image_paths": [],
            "camera_id": "cam-test",
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


def test_no_detection_passes_without_human_review():
    repository = MockQCRepository()
    graph = build_qc_graph(repository=repository, checkpointer=InMemorySaver())
    thread_id = str(uuid4())
    result = graph.invoke(
        {
            "thread_id": thread_id,
            "inspection_id": str(uuid4()),
            "vehicle_id": "TEST-PILOT-NO-DETECTION",
            "image_url": IMAGE_URL,
            "camera_id": "cam-test",
            "mock_scenario": "no_defect",
            "auto_pass_enabled": False,
            "execution_trace": [],
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    assert result["decision"] == "PASS"
    assert result["final_status"] == "PASS"


def test_high_confidence_defect_generates_recommendation():
    _, repository, thread_id, _, result = run_scenario("high_confidence")
    assert result["decision"] == "DEFECT_CONFIRMED"
    assert result["suggested_defect_codes"][0]["defect_code"] == "DENT01"
    assert result["verify_count"] == 0
    assert result["recommendation_code"] == "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT"
    assert result["recommendation"] == "Hold the vehicle and transfer it to Body Repair for technical assessment"
    assert "ISOLATE_FOR_BODY_REPAIR_ASSESSMENT" not in result["reason"]
    assert result["policy_decision"]["policy_id"] == "FNS-GEOMETRY-001"
    assert result["policy_decision"]["production_eligible"] is False
    assert result["ai_analysis"]["provider"] == "deterministic"
    assert repository.get(thread_id)["final_status"] == "HOLD_FOR_REWORK"


def test_known_medium_confidence_is_classified_without_verification():
    _, _, _, _, result = run_scenario("medium_confirmed")
    assert result["verify_count"] == 0
    assert result["classified_defect_code"].startswith("SCRATCH")
    assert result["recommendation_code"] == "SURFACE_DAMAGE_ASSESSMENT_AND_REINSPECT"
    assert result["recommendation"] == "Hold for controlled surface assessment and documented reinspection"
    assert result["policy_decision"]["policy_id"] == "FNS-SURFACE-001"
    trace_nodes = [event["node"] for event in result["execution_trace"]]
    assert trace_nodes.count("verify_defect") == 0
    assert trace_nodes.count("assess_result") == 1


def test_unknown_defect_interrupts_and_resumes_hitl():
    graph, repository, thread_id, config, result = run_scenario("unknown_defect")
    assert result["verify_count"] == 0
    assert result["human_required"] is True
    assert result["policy_decision"]["document_review"]["query"] == {
        "vehicle_model": "SUV_EV_2026",
        "defect_type": "unknown",
    }
    assert result["policy_decision"]["document_review"]["approved_checklist"]
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
    assert resumed["recommendation_code"] == "MANUAL_VISUAL_REINSPECTION"
    assert resumed["recommendation"] == "Keep the vehicle on hold and perform a new manual visual inspection"
    assert repository.get(thread_id)["final_status"] == "HOLD_FOR_QC"
