from __future__ import annotations

from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from agent.graph.builder import build_qc_graph
from agent.services.repository import MockQCRepository
from agent.services.vision_verifier import MockVisionVerifier

IMAGE_URL = "/test-fixtures/inspection.jpg"


def run_scenario(scenario: str, vision_scenario: str | None):
    repository = MockQCRepository()
    graph = build_qc_graph(
        repository=repository,
        checkpointer=InMemorySaver(),
        vision=MockVisionVerifier(),
    )
    thread_id = str(uuid4())
    state: dict[str, object] = {
        "thread_id": thread_id,
        "inspection_id": str(uuid4()),
        "vehicle_id": f"TEST-{scenario}",
        "vehicle_model": "SUV_EV_2026",
        "image_url": IMAGE_URL,
        "image_paths": [],
        "camera_id": "cam-test",
        "mock_scenario": scenario,
        "execution_trace": [],
    }
    if vision_scenario is not None:
        state["mock_vision_scenario"] = vision_scenario
    result = graph.invoke(state, config={"configurable": {"thread_id": thread_id}})
    return result, repository, thread_id


def test_vision_supported_does_not_change_baseline_outcome():
    result, repository, thread_id = run_scenario("high_confidence", "supported")
    assert result["decision"] == "DEFECT_CONFIRMED"
    assert result["agent_vision_status"] == "COMPLETED"
    assert result["visual_assessment"]["visual_verification"] == "SUPPORTED"
    assert repository.get(thread_id)["final_status"] == "HOLD_FOR_REWORK"


def test_vision_conflict_forces_hitl_even_on_confirmed_route():
    result, _, _ = run_scenario("high_confidence", "conflict")
    assert result["decision"] == "VISUAL_LLM_CONFLICT_REQUIRES_HITL"
    assert result["human_required"] is True
    assert result["hitl_status"] == "PENDING"
    assert result["__interrupt__"][0].value["type"] == "visual_qc_review"


def test_vision_high_uncertainty_forces_hitl():
    result, _, _ = run_scenario("high_confidence", "uncertain_high")
    assert result["decision"] == "VISUAL_LLM_UNCERTAINTY_HIGH_REQUIRES_HITL"
    assert result["human_required"] is True
    assert result["hitl_status"] == "PENDING"


def test_vision_unavailable_forces_hitl():
    result, _, _ = run_scenario("high_confidence", "unavailable")
    assert result["decision"] == "VISION_LLM_UNAVAILABLE"
    assert result["agent_vision_status"] == "UNAVAILABLE_REQUIRES_HITL"
    assert result["human_required"] is True


def test_vision_skipped_when_no_defect_detected():
    result, _, _ = run_scenario("no_defect", "conflict")
    assert result["decision"] == "PASS"
    assert result["agent_vision_status"] == "SKIPPED_NO_DEFECT"


def test_vision_not_configured_by_default_matches_prior_behavior():
    """Regression guard: the default NoopVisionVerifier must not alter routing."""
    repository = MockQCRepository()
    graph = build_qc_graph(repository=repository, checkpointer=InMemorySaver())
    thread_id = str(uuid4())
    result = graph.invoke(
        {
            "thread_id": thread_id,
            "inspection_id": str(uuid4()),
            "vehicle_id": "TEST-default",
            "vehicle_model": "SUV_EV_2026",
            "image_url": IMAGE_URL,
            "image_paths": [],
            "camera_id": "cam-test",
            "mock_scenario": "high_confidence",
            "execution_trace": [],
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    assert result["decision"] == "DEFECT_CONFIRMED"
    assert result["agent_vision_status"] == "NOT_CONFIGURED"
    assert result["visual_assessment"] is None
