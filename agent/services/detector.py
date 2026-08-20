from __future__ import annotations

from typing import Any, Protocol

from agent.graph.state import QCState


class DetectorService(Protocol):
    def detect(self, state: QCState) -> dict[str, Any]: ...


class MockDetector:
    """YOLO/segmentation adapter boundary with deterministic demo scenarios."""

    _SCENARIOS: dict[str, dict[str, Any]] = {
        "no_defect": {
            "defect_detected": False,
            "defect_type": "none",
            "confidence": 0.99,
            "bbox": None,
            "severity": "NONE",
        },
        "high_confidence": {
            "defect_detected": True,
            "defect_type": "dent",
            "confidence": 0.94,
            "bbox": {"x1": 220.0, "y1": 145.0, "x2": 405.0, "y2": 365.0},
            "severity": "P",
        },
        "medium_confirmed": {
            "defect_detected": True,
            "defect_type": "scratch",
            "confidence": 0.68,
            "bbox": {"x1": 265.0, "y1": 255.0, "x2": 495.0, "y2": 425.0},
            "severity": "C",
        },
        "verify_uncertain": {
            "defect_detected": True,
            "defect_type": "dent",
            "confidence": 0.63,
            "bbox": {"x1": 85.0, "y1": 265.0, "x2": 375.0, "y2": 510.0},
            "severity": "UNCONFIRMED",
        },
        "low_confidence": {
            "defect_detected": True,
            "defect_type": "scratch",
            "confidence": 0.32,
            "bbox": {"x1": 225.0, "y1": 430.0, "x2": 615.0, "y2": 615.0},
            "severity": "UNCONFIRMED",
        },
        "unknown_defect": {
            "defect_detected": True,
            "defect_type": "unknown",
            "confidence": 0.91,
            "bbox": {"x1": 180.0, "y1": 180.0, "x2": 360.0, "y2": 340.0},
            "severity": "UNASSESSED",
        },
    }

    def detect(self, state: QCState) -> dict[str, Any]:
        scenario = state.get("mock_scenario", "high_confidence")
        base = dict(self._SCENARIOS.get(scenario, self._SCENARIOS["high_confidence"]))
        cameras = state.get("camera_evidence") or [{
            "camera_id": state.get("camera_id", "cam-fns-01"),
            "image_url": state.get("image_url", ""),
        }]
        camera_results: list[dict[str, Any]] = []
        detections: list[dict[str, Any]] = []
        for camera in cameras:
            camera_detection = dict(base)
            camera_detection["camera_id"] = str(camera["camera_id"])
            camera_detection["image_url"] = str(camera.get("image_url", ""))
            camera_detection["detections"] = []
            if base["defect_detected"]:
                item = {
                    "detection_id": f"{camera['camera_id']}::0",
                    "camera_id": str(camera["camera_id"]),
                    "class_name": base["defect_type"],
                    "raw_class_name": base["defect_type"],
                    "confidence": base["confidence"],
                    "bbox": base["bbox"],
                    "segmentation": None,
                }
                camera_detection["detections"] = [item]
                detections.append(item)
            camera_results.append(camera_detection)
        groups = [
            {
                "defect_type": base["defect_type"],
                "observation_count": len(detections),
                "camera_ids": [item["camera_id"] for item in detections],
                "deduplication_status": (
                    "CANDIDATE_DUPLICATE_REQUIRES_CALIBRATION"
                    if len(detections) > 1 else "SINGLE_VIEW"
                ),
            }
        ] if detections else []
        primary_camera_id = str(detections[0]["camera_id"]) if detections else str(cameras[0]["camera_id"])
        primary_detection_id = detections[0]["detection_id"] if detections else None
        return {
            **base,
            "detections": detections,
            "camera_results": camera_results,
            "finding_groups": groups,
            "camera_id": primary_camera_id,
            "primary_detection_id": primary_detection_id,
            "image_width": 640,
            "image_height": 640,
            "inference_status": "SUCCESS",
        }
