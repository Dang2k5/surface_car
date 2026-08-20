"""Regression tests for the two multi-camera correctness fixes:

1. The vision LLM cross-check must resolve the image of the camera that
   produced the *primary* defect, not always camera[0].
2. `enriched_defects` must not fabricate a severity for camera views that
   were not the primary defect, and must mark exactly one item `is_primary`.
3. `GroqReasoningService.analyze()` must give the final decision LLM
   visibility into cross-camera evidence (`cross_camera_findings`,
   `total_camera_views`), not just the primary defect.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from agent.graph.builder import build_qc_graph
from agent.graph.nodes import _enrich_defects
from agent.services.image_source import camera_image_source
from agent.services.policy import PolicyCatalog
from agent.services.reasoning import GroqReasoningService
from agent.services.repository import MockQCRepository
from agent.services.vision_verifier import GroqVisionVerifierService

ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000155273de50000000049454e44ae426082"
)


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        message = SimpleNamespace(content=self._content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class _FakeGroqClient:
    def __init__(self, content: str) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(content))


def _write_camera_images(tmp_path):
    front = tmp_path / "front.png"
    rear = tmp_path / "rear.png"
    front.write_bytes(ONE_PIXEL_PNG)
    rear.write_bytes(ONE_PIXEL_PNG)
    return front, rear


def test_camera_image_source_resolves_the_matching_camera_not_the_first(tmp_path):
    front, rear = _write_camera_images(tmp_path)
    state = {
        "camera_evidence": [
            {"camera_id": "CAM-FRONT", "image_path": str(front), "image_url": ""},
            {"camera_id": "CAM-REAR", "image_path": str(rear), "image_url": ""},
        ]
    }

    assert camera_image_source(state, "CAM-REAR") == str(rear.resolve())
    assert camera_image_source(state, "CAM-FRONT") == str(front.resolve())


def test_camera_image_source_falls_back_to_first_camera_when_unmatched(tmp_path):
    front, _rear = _write_camera_images(tmp_path)
    state = {
        "camera_evidence": [
            {"camera_id": "CAM-FRONT", "image_path": str(front), "image_url": ""},
        ]
    }

    assert camera_image_source(state, "CAM-UNKNOWN") == str(front.resolve())
    assert camera_image_source(state, None) == str(front.resolve())


def test_vision_verifier_loads_the_primary_camera_image_not_camera_zero(tmp_path):
    front, rear = _write_camera_images(tmp_path)
    payload = json.dumps(
        {
            "visual_verification": "SUPPORTED",
            "visual_uncertainty": "LOW",
        }
    )
    service = GroqVisionVerifierService(api_key="test", model="test-vision-model")
    fake_client = _FakeGroqClient(payload)
    service.client = fake_client

    state = {
        "camera_evidence": [
            {"camera_id": "CAM-FRONT", "image_path": str(front), "image_url": ""},
            {"camera_id": "CAM-REAR", "image_path": str(rear), "image_url": ""},
        ],
        # The primary defect was found on the SECOND camera, not the first.
        "camera_id": "CAM-REAR",
        "defect_type": "dent",
        "confidence": 0.9,
        "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
        "zone_name": "rear_bumper",
    }

    service.verify_visual(state)

    sent_messages = fake_client.chat.completions.last_kwargs["messages"]
    image_content = next(
        part
        for message in sent_messages
        if isinstance(message.get("content"), list)
        for part in message["content"]
        if part.get("type") == "image_url"
    )
    sent_data_uri = image_content["image_url"]["url"]
    # The data URI must be derived from rear.png's bytes, not front.png's.
    import base64

    expected_b64 = base64.b64encode(rear.read_bytes()).decode("ascii")
    assert expected_b64 in sent_data_uri


def test_enrich_defects_marks_only_the_primary_detection_and_hides_other_severities():
    state = {
        "zone_name": "front_door",
        "severity": "P",
        "primary_detection_id": "CAM-FRONT::0",
        "detections": [
            {
                "detection_id": "CAM-FRONT::0",
                "camera_id": "CAM-FRONT",
                "class_name": "dent",
                "confidence": 0.9,
                "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            },
            {
                "detection_id": "CAM-REAR::0",
                "camera_id": "CAM-REAR",
                "class_name": "dent",
                "confidence": 0.85,
                "bbox": {"x1": 1, "y1": 1, "x2": 11, "y2": 11},
            },
        ],
    }

    enriched = _enrich_defects(state)

    by_detection_id = {item["detection_id"]: item for item in enriched}
    assert by_detection_id["CAM-FRONT::0"]["is_primary"] is True
    assert by_detection_id["CAM-FRONT::0"]["severity_rank"] == "P"
    assert by_detection_id["CAM-REAR::0"]["is_primary"] is False
    assert by_detection_id["CAM-REAR::0"]["severity_rank"] == "UNCLASSIFIED_SECONDARY_FINDING"


def test_reasoning_analyze_prompt_includes_cross_camera_findings():
    state = {
        "defect_type": "dent",
        "confidence": 0.9,
        "severity": "P",
        "camera_results": [{"camera_id": "CAM-FRONT"}, {"camera_id": "CAM-REAR"}],
        "finding_groups": [
            {
                "defect_type": "dent",
                "observation_count": 2,
                "camera_ids": ["CAM-FRONT", "CAM-REAR"],
                "deduplication_status": "CANDIDATE_DUPLICATE_REQUIRES_CALIBRATION",
            }
        ],
    }
    policy = PolicyCatalog().evaluate(state)
    payload = json.dumps(
        {
            "summary_en": "ok",
            "summary_vi": "ok",
            "risk_flags": [],
            "recommended_checks": [],
            "cited_source_ids": [],
            "severity": "P",
            "action_code": policy.action_code,
            "action_label": policy.action_label,
            "final_status": policy.final_status,
            "allow_test_drive": False,
            "decision_rationale_vi": "ok",
        }
    )
    service = GroqReasoningService(api_key="test", model="test-reasoning-model")
    fake_client = _FakeGroqClient(payload)
    service.client = fake_client

    service.analyze(state, policy)

    sent_prompt = json.loads(fake_client.chat.completions.last_kwargs["messages"][1]["content"])
    inspection = sent_prompt["inspection"]
    assert inspection["total_camera_views"] == 2
    assert inspection["cross_camera_findings"][0]["camera_ids"] == ["CAM-FRONT", "CAM-REAR"]
    assert inspection["cross_camera_findings"][0]["deduplication_status"] == (
        "CANDIDATE_DUPLICATE_REQUIRES_CALIBRATION"
    )


def test_multi_camera_graph_run_exposes_all_camera_findings_with_one_primary():
    repository = MockQCRepository()
    graph = build_qc_graph(repository=repository, checkpointer=InMemorySaver())
    thread_id = str(uuid4())
    state = {
        "thread_id": thread_id,
        "inspection_id": str(uuid4()),
        "vehicle_id": "TEST-multi-camera",
        "vehicle_model": "SUV_EV_2026",
        "image_url": "/assets/objects/inspections/x/camera-0.png",
        "image_paths": [],
        "camera_evidence": [
            {"camera_id": "CAM-FRONT", "image_url": "/assets/objects/f.png", "image_path": ""},
            {"camera_id": "CAM-REAR", "image_url": "/assets/objects/r.png", "image_path": ""},
        ],
        "camera_id": "CAM-FRONT",
        "mock_scenario": "high_confidence",
        "execution_trace": [],
    }

    result = graph.invoke(state, config={"configurable": {"thread_id": thread_id}})

    enriched = result["enriched_defects"]
    assert len(enriched) == 2
    primaries = [item for item in enriched if item["is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["camera_id"] == "CAM-FRONT"
    secondary = next(item for item in enriched if not item["is_primary"])
    assert secondary["severity_rank"] == "UNCLASSIFIED_SECONDARY_FINDING"
    assert result["finding_groups"][0]["camera_ids"] == ["CAM-FRONT", "CAM-REAR"]
