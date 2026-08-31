from __future__ import annotations

from typing import Any

from dotenv import load_dotenv
from langgraph.types import Command

# tests/conftest.py's autouse fixture needs DATABASE_URL for its throwaway-schema
# isolation even though this file never touches the database -- other test files get
# this for free via `from backend.app.main import app` (main.py calls load_dotenv() at
# import time); load it explicitly here instead of relying on that import side effect.
load_dotenv()

from agent.graph.builder import build_qc_graph
from agent.services.reasoning import DeterministicReasoningService

# This project only classifies scratch/dent (agent/services/yolo_detector.py's
# CLASS_MAP) -- these scenarios stay entirely inside that domain and instead vary
# SEVERITY (small / medium-large / cluster) to exercise all three routing outcomes,
# mirroring the 3-tier split in agent/policies/qc_policy_catalog.json:
#   SCRATCH01/DENT01 (small)          -> PASS  (FNS-*-PASS-001)
#   SCRATCH02-03/DENT02-03 (med/large) -> FAIL  (FNS-SURFACE-001 / FNS-GEOMETRY-001)
#   SCRATCH04-05/DENT04-05 (cluster/crease) -> HITL (FNS-*-HITL-001, human_required=true)


class _UnusedDetector:
    """Every scenario below supplies precomputed_detection, so detect_defect must
    never fall back to calling the real detector (agent/graph/nodes.py:detect_defect)."""

    def detect(self, state: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("detector.detect() should not run when precomputed_detection is set")


class _UnusedVerifier:
    def verify(self, state: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("verify_defect is never reached by PASS/CONFIRMED/HITL routing")


class _InMemoryQCRepository:
    def __init__(self) -> None:
        self.saved: dict[str, dict[str, Any]] = {}

    def save(self, state: dict[str, Any]) -> None:
        self.saved[state["thread_id"]] = dict(state)

    def get(self, thread_id: str) -> dict[str, Any] | None:
        return self.saved.get(thread_id)

    def list(self) -> list[dict[str, Any]]:
        return list(self.saved.values())

    def list_with_metadata(self) -> list[dict[str, Any]]:
        return list(self.saved.values())

    def clear(self) -> int:
        count = len(self.saved)
        self.saved.clear()
        return count


def _config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _detection(index: int, class_name: str, width_mm: float) -> dict[str, Any]:
    return {
        "detection_id": f"CAM-01_{index}",
        "camera_id": "CAM-01",
        "class_name": class_name,
        "raw_class_name": class_name,
        "confidence": 0.9,
        "bbox": {"x1": 10.0, "y1": 10.0, "x2": 10.0 + width_mm, "y2": 40.0},
        "visual_measurements": {
            "estimated_width_mm": width_mm,
            "estimated_length_mm": width_mm,
            "relative_position": "middle_center",
        },
        "segmentation": {"format": "polygon", "points": []},
    }


def _precomputed_clean() -> dict[str, Any]:
    camera_results = [
        {
            "camera_id": "CAM-01",
            "image_url": "https://example.test/clean.jpg",
            "image_width": 1280,
            "image_height": 960,
            "defect_detected": False,
            "detections": [],
        }
    ]
    return {
        "detections": [],
        "camera_results": camera_results,
        "finding_groups": [],
        "camera_id": "CAM-01",
        "primary_detection_id": None,
        "image_width": 1280,
        "image_height": 960,
        "inference_ms": 5.0,
        "inference_status": "SUCCESS",
        "defect_detected": False,
        "defect_type": "none",
        "raw_class_name": None,
        "confidence": 0.0,
        "bbox": None,
        "segmentation_result": None,
        "visual_measurements": {},
        "severity": "UNASSESSED",
    }


def _precomputed(class_name: str, widths_mm: list[float]) -> dict[str, Any]:
    detections = [_detection(i, class_name, width) for i, width in enumerate(widths_mm)]
    camera_results = [
        {
            "camera_id": "CAM-01",
            "image_url": "https://example.test/defect.jpg",
            "image_width": 1280,
            "image_height": 960,
            "defect_detected": True,
            "detections": detections,
        }
    ]
    primary = detections[0]
    return {
        "detections": detections,
        "camera_results": camera_results,
        "finding_groups": [],
        "camera_id": "CAM-01",
        "primary_detection_id": primary["detection_id"],
        "image_width": 1280,
        "image_height": 960,
        "inference_ms": 5.0,
        "inference_status": "SUCCESS",
        "defect_detected": True,
        "defect_type": class_name,
        "raw_class_name": class_name,
        "confidence": primary["confidence"],
        "bbox": primary["bbox"],
        "segmentation_result": primary["segmentation"],
        "visual_measurements": primary["visual_measurements"],
        "severity": "UNASSESSED",
    }


def _initial_state(thread_id: str, precomputed: dict[str, Any]) -> dict[str, Any]:
    return {
        "inspection_id": f"insp-{thread_id}",
        "thread_id": thread_id,
        "vehicle_id": f"veh-{thread_id}",
        "vehicle_model": "unknown_model",
        "station_id": "STATION-01",
        "image_url": "https://example.test/defect.jpg",
        "image_paths": [],
        "camera_id": "CAM-01",
        "zone_name": "unknown_zone",
        "precomputed_detection": precomputed,
        "force_human_review": False,
        "retry_count": 0,
        "max_retries": 2,
    }


def _build_graph():
    return build_qc_graph(
        detector=_UnusedDetector(),
        verifier=_UnusedVerifier(),
        repository=_InMemoryQCRepository(),
        reasoning=DeterministicReasoningService(),
    )


def test_no_defect_detected_passes_without_any_policy_lookup():
    graph = _build_graph()
    thread_id = "no-defect"
    result = graph.invoke(_initial_state(thread_id, _precomputed_clean()), config=_config(thread_id))
    assert result.get("__interrupt__") in (None, ())
    assert result["assessment_route"] == "PASS"
    assert result["final_status"] == "PASS"
    assert result["hitl_status"] == "CONFIRMED"
    assert result["human_required"] is False


def test_small_scratch_passes_within_tolerance():
    # width 20mm -> SCRATCH01 -> FNS-SURFACE-PASS-001 (PASS): a real, catalog-confirmed
    # defect that the policy explicitly allows, distinct from PASS-by-no-detection above.
    graph = _build_graph()
    thread_id = "scratch-small-pass"
    result = graph.invoke(
        _initial_state(thread_id, _precomputed("scratch", [20.0])), config=_config(thread_id)
    )
    assert result.get("__interrupt__") in (None, ())
    assert result["assessment_route"] == "CONFIRMED"
    assert result["final_status"] == "PASS"
    assert result["policy_decision"]["policy_id"] == "FNS-SURFACE-PASS-001"
    assert result["human_required"] is False


def test_medium_scratch_fails():
    # width 70mm -> SCRATCH02 -> FNS-SURFACE-001 (FAIL).
    graph = _build_graph()
    thread_id = "scratch-medium-fail"
    result = graph.invoke(
        _initial_state(thread_id, _precomputed("scratch", [70.0])), config=_config(thread_id)
    )
    assert result.get("__interrupt__") in (None, ())
    assert result["assessment_route"] == "CONFIRMED"
    assert result["final_status"] == "FAIL"
    assert result["policy_decision"]["policy_id"] == "FNS-SURFACE-001"
    assert result["human_required"] is False


def test_small_dent_passes_within_tolerance():
    # width 10mm -> DENT01 -> FNS-GEOMETRY-PASS-001 (PASS).
    graph = _build_graph()
    thread_id = "dent-small-pass"
    result = graph.invoke(
        _initial_state(thread_id, _precomputed("dent", [10.0])), config=_config(thread_id)
    )
    assert result.get("__interrupt__") in (None, ())
    assert result["assessment_route"] == "CONFIRMED"
    assert result["final_status"] == "PASS"
    assert result["policy_decision"]["policy_id"] == "FNS-GEOMETRY-PASS-001"
    assert result["human_required"] is False


def test_medium_dent_fails():
    # width 40mm -> DENT02 -> FNS-GEOMETRY-001 (FAIL).
    graph = _build_graph()
    thread_id = "dent-medium-fail"
    result = graph.invoke(
        _initial_state(thread_id, _precomputed("dent", [40.0])), config=_config(thread_id)
    )
    assert result.get("__interrupt__") in (None, ())
    assert result["assessment_route"] == "CONFIRMED"
    assert result["final_status"] == "FAIL"
    assert result["policy_decision"]["policy_id"] == "FNS-GEOMETRY-001"
    assert result["human_required"] is False


def test_scratch_cluster_has_no_automated_disposition_and_routes_to_hitl():
    # >=2 scratch detections -> DeterministicReasoningService picks SCRATCH04 (cluster) ->
    # FNS-SURFACE-HITL-001 sets human_required=true -- this is exactly the fail-safe that
    # agent/graph/nodes.py's assess_result must catch and route to human_review instead
    # of silently auto-saving a FAIL.
    graph = _build_graph()
    thread_id = "scratch-cluster-hitl"
    config = _config(thread_id)
    result = graph.invoke(
        _initial_state(thread_id, _precomputed("scratch", [20.0, 25.0])), config=config
    )

    interrupts = result.get("__interrupt__")
    assert interrupts, "expected the graph to pause at human_review, but it ran to completion"
    snapshot = graph.get_state(config)
    state = snapshot.values
    assert state["assessment_route"] == "HITL"
    assert state["decision"] == "MANUAL_REINSPECTION_REQUIRED"
    assert state["hitl_status"] == "PENDING"
    assert state["human_required"] is True
    assert state["policy_decision"]["policy_id"] == "FNS-SURFACE-HITL-001"

    resumed = graph.invoke(
        Command(resume={"action": "APPROVE", "reason": "QC đã xác nhận cụm vết xước thật."}),
        config=config,
    )
    assert resumed.get("__interrupt__") in (None, ())
    assert resumed["hitl_status"] == "CONFIRMED"
    assert resumed["final_status"] == "FAIL"


def test_dent_cluster_has_no_automated_disposition_and_routes_to_hitl():
    # >=2 dent detections -> DENT05 (cluster) -> FNS-GEOMETRY-HITL-001 (human_required=true).
    graph = _build_graph()
    thread_id = "dent-cluster-hitl"
    config = _config(thread_id)
    result = graph.invoke(
        _initial_state(thread_id, _precomputed("dent", [15.0, 18.0])), config=config
    )

    interrupts = result.get("__interrupt__")
    assert interrupts, "expected the graph to pause at human_review, but it ran to completion"
    snapshot = graph.get_state(config)
    state = snapshot.values
    assert state["assessment_route"] == "HITL"
    assert state["decision"] == "MANUAL_REINSPECTION_REQUIRED"
    assert state["human_required"] is True
    assert state["policy_decision"]["policy_id"] == "FNS-GEOMETRY-HITL-001"
