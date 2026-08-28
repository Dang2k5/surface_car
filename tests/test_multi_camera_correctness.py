"""Regression tests for multi-camera correctness fixes:

1. `camera_image_source` must resolve the image of the camera that
   produced the *primary* defect, not always camera[0].
2. `enriched_defects` must give a REAL severity + is_primary=True to every camera
   that has its own independently classified finding (state["camera_classifications"]),
   not just the single global-worst detection — and must still never fabricate a
   severity for a detection that lost out to another one WITHIN the same camera.
"""
from __future__ import annotations

from agent.graph.nodes import _enrich_defects
from agent.services.image_source import camera_image_source

ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000155273de50000000049454e44ae426082"
)


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


def test_enrich_defects_gives_every_classified_camera_its_own_real_severity():
    # CAM-FRONT and CAM-REAR are two DIFFERENT camera mounts, each independently
    # classified by QCNodes.detect_defect — both must surface as real findings, not
    # just whichever one happens to be the single global-worst detection.
    state = {
        "zone_name": "front_door",
        "camera_classifications": [
            {"detection_id": "CAM-FRONT::0", "camera_id": "CAM-FRONT", "severity": "A"},
            {"detection_id": "CAM-REAR::0", "camera_id": "CAM-REAR", "severity": "C"},
        ],
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
            # A second, lower-priority detection on CAM-FRONT that was NOT the camera's
            # own local-worst finding — this one must still get no fabricated severity.
            {
                "detection_id": "CAM-FRONT::1",
                "camera_id": "CAM-FRONT",
                "class_name": "scratch",
                "confidence": 0.5,
                "bbox": {"x1": 20, "y1": 20, "x2": 30, "y2": 30},
            },
        ],
    }

    enriched = _enrich_defects(state)

    by_detection_id = {item["detection_id"]: item for item in enriched}
    assert by_detection_id["CAM-FRONT::0"]["is_primary"] is True
    assert by_detection_id["CAM-FRONT::0"]["severity_rank"] == "A"
    assert by_detection_id["CAM-REAR::0"]["is_primary"] is True
    assert by_detection_id["CAM-REAR::0"]["severity_rank"] == "C"
    assert by_detection_id["CAM-FRONT::1"]["is_primary"] is False
    assert by_detection_id["CAM-FRONT::1"]["severity_rank"] == "UNCLASSIFIED_SECONDARY_FINDING"
