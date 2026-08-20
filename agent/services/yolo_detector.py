from __future__ import annotations

import hashlib
import math
import time
from pathlib import Path
from threading import Lock
from typing import Any

from agent.graph.state import QCState
from agent.services.image_source import camera_evidence as _camera_evidence
from agent.services.image_source import resolve_image_source as _resolve_image_source

CLASS_MAP = {
    "dent": "dent",
    "scratch": "scratch",
}
SAFETY_PRIORITY = {
    "dent": 30,
    "scratch": 10,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sample_polygon(points: Any, max_points: int = 128) -> list[list[float]]:
    values = points.tolist() if hasattr(points, "tolist") else list(points)
    if not values:
        return []
    step = max(1, math.ceil(len(values) / max_points))
    return [[round(float(x), 2), round(float(y), 2)] for x, y in values[::step]]


def _relative_position(center_x: float, center_y: float) -> str:
    horizontal = "left" if center_x < 1 / 3 else "right" if center_x > 2 / 3 else "center"
    vertical = "upper" if center_y < 1 / 3 else "lower" if center_y > 2 / 3 else "middle"
    return f"{vertical}_{horizontal}"


def _polygon_area(points: list[list[float]]) -> float:
    """Return polygon area in pixels using the shoelace formula."""
    if len(points) < 3:
        return 0.0
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    ) / 2


class LocalYoloSegmentationDetector:
    """Ultralytics segmentation adapter that normalizes model output into QCState."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        device: str = "cpu",
        confidence: float = 0.25,
        image_size: int = 640,
        fixed_calibration_enabled: bool = True,
        mm_per_pixel_x: float = 0.8,
        mm_per_pixel_y: float = 0.8,
        calibration_profile_id: str = "FNS_FRONT_PILOT_1280",
    ) -> None:
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"YOLO model not found: {path}")
        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError(
                "Ultralytics is required for DETECTOR_PROVIDER=local_yolo. "
                "Install dependencies from requirements.txt."
            ) from error

        self.model_path = path.resolve()
        self.device = device
        self.confidence = confidence
        self.image_size = image_size
        if mm_per_pixel_x <= 0 or mm_per_pixel_y <= 0:
            raise ValueError("Camera calibration factors must be greater than zero")
        self.fixed_calibration_enabled = fixed_calibration_enabled
        self.mm_per_pixel_x = mm_per_pixel_x
        self.mm_per_pixel_y = mm_per_pixel_y
        self.calibration_profile_id = calibration_profile_id
        self.model_version = _sha256(self.model_path)[:12]
        self.model = YOLO(str(self.model_path))
        self._lock = Lock()

    def detect(self, state: QCState) -> dict[str, Any]:
        evidence = _camera_evidence(state)
        sources = [
            _resolve_image_source(item["image_path"] or None, item["image_url"])
            for item in evidence
        ]
        started = time.perf_counter()
        with self._lock:
            results = self.model.predict(
                source=sources[0] if len(sources) == 1 else sources,
                conf=self.confidence,
                imgsz=self.image_size,
                device=self.device,
                verbose=False,
            )
        inference_ms = round((time.perf_counter() - started) * 1000, 1)
        if not results:
            raise RuntimeError("YOLO returned no Results object")

        if len(results) != len(evidence):
            raise RuntimeError("YOLO result count does not match the submitted camera views")

        camera_results: list[dict[str, Any]] = []
        detections: list[dict[str, Any]] = []
        for result, camera in zip(results, evidence, strict=True):
            height, width = (int(value) for value in result.orig_shape)
            camera_detections: list[dict[str, Any]] = []
            boxes = result.boxes
            masks = result.masks
            if boxes is not None:
                xyxy_values = boxes.xyxy.cpu().tolist()
                confidence_values = boxes.conf.cpu().tolist()
                class_values = boxes.cls.cpu().tolist()
                polygons = masks.xy if masks is not None else []
                for index, (xyxy, score, class_value) in enumerate(
                    zip(xyxy_values, confidence_values, class_values, strict=True)
                ):
                    class_id = int(class_value)
                    raw_name = str(self.model.names[class_id])
                    normalized_name = CLASS_MAP.get(raw_name.strip().lower(), "unknown")
                    if normalized_name == "unknown":
                        continue
                    polygon = _sample_polygon(polygons[index]) if index < len(polygons) else []
                    x1, y1, x2, y2 = (float(value) for value in xyxy)
                    box_width = max(0.0, x2 - x1)
                    box_height = max(0.0, y2 - y1)
                    center_x_ratio = ((x1 + x2) / 2) / max(1, width)
                    center_y_ratio = ((y1 + y2) / 2) / max(1, height)
                    mask_area_px = _polygon_area(polygon)
                    physical_measurements = (
                        {
                            "estimated_width_mm": round(box_width * self.mm_per_pixel_x, 2),
                            "estimated_height_mm": round(box_height * self.mm_per_pixel_y, 2),
                            "estimated_length_mm": round(
                                max(
                                    box_width * self.mm_per_pixel_x,
                                    box_height * self.mm_per_pixel_y,
                                ),
                                2,
                            ),
                            "estimated_bbox_area_mm2": round(
                                box_width
                                * box_height
                                * self.mm_per_pixel_x
                                * self.mm_per_pixel_y,
                                2,
                            ),
                            "estimated_mask_area_mm2": (
                                round(
                                    mask_area_px
                                    * self.mm_per_pixel_x
                                    * self.mm_per_pixel_y,
                                    2,
                                )
                                if mask_area_px > 0
                                else None
                            ),
                            "mm_per_pixel_x": self.mm_per_pixel_x,
                            "mm_per_pixel_y": self.mm_per_pixel_y,
                            "calibration_profile_id": self.calibration_profile_id,
                            "physical_size_status": (
                                "PILOT_FIXED_CAMERA_ESTIMATE_NOT_QC_APPROVED"
                            ),
                        }
                        if self.fixed_calibration_enabled
                        else {
                            "physical_size_status": "REQUIRES_CAMERA_CALIBRATION"
                        }
                    )
                    camera_detections.append(
                        {
                            "detection_id": f"{camera['camera_id']}::{index}",
                            "camera_id": camera["camera_id"],
                            "class_id": class_id,
                            "raw_class_name": raw_name,
                            "class_name": normalized_name,
                            "confidence": round(float(score), 6),
                            "bbox": {
                                "x1": round(x1, 2),
                                "y1": round(y1, 2),
                                "x2": round(x2, 2),
                                "y2": round(y2, 2),
                            },
                            "visual_measurements": {
                                "width_px": round(box_width, 2),
                                "height_px": round(box_height, 2),
                                "bbox_area_px": round(box_width * box_height, 2),
                                "mask_area_px": round(mask_area_px, 2),
                                "image_area_ratio": round(
                                    (box_width * box_height) / max(1, width * height), 6
                                ),
                                "center_x_ratio": round(center_x_ratio, 6),
                                "center_y_ratio": round(center_y_ratio, 6),
                                "relative_position": _relative_position(
                                    center_x_ratio, center_y_ratio
                                ),
                                **physical_measurements,
                            },
                            "segmentation": {"format": "polygon", "points": polygon},
                        }
                    )
            camera_results.append(
                {
                    "camera_id": camera["camera_id"],
                    "image_url": camera["image_url"],
                    "image_width": width,
                    "image_height": height,
                    "defect_detected": bool(camera_detections),
                    "detections": camera_detections,
                }
            )
            detections.extend(camera_detections)

        primary = max(
            detections,
            key=lambda item: (SAFETY_PRIORITY.get(item["class_name"], 0), item["confidence"]),
            default=None,
        )
        primary_camera = next(
            (item for item in camera_results if primary and item["camera_id"] == primary["camera_id"]),
            camera_results[0],
        )
        common = {
            "detections": detections,
            "camera_results": camera_results,
            "finding_groups": _group_findings(detections),
            "camera_id": primary_camera["camera_id"],
            "primary_detection_id": primary["detection_id"] if primary else None,
            "image_width": primary_camera["image_width"],
            "image_height": primary_camera["image_height"],
            "model_name": self.model_path.name,
            "model_version": self.model_version,
            "model_task": str(getattr(self.model, "task", "segment")),
            "inference_ms": inference_ms,
            "inference_status": "SUCCESS",
        }
        if primary is None:
            return {
                **common,
                "defect_detected": False,
                "defect_type": "none",
                "raw_class_name": None,
                "confidence": 0.0,
                "bbox": None,
                "segmentation_result": None,
                "severity": "UNASSESSED",
            }
        return {
            **common,
            "defect_detected": True,
            "defect_type": primary["class_name"],
            "raw_class_name": primary["raw_class_name"],
            "confidence": primary["confidence"],
            "bbox": primary["bbox"],
            "segmentation_result": primary["segmentation"],
            "visual_measurements": primary["visual_measurements"],
            "severity": "UNASSESSED",
        }


def _group_findings(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group cross-view observations without falsely claiming physical deduplication.

    The same defect cannot be proved identical between camera perspectives until
    the station has calibrated camera geometry or inspection-zone coordinates. The Agent
    therefore preserves each observation and labels multi-view matches as
    candidates for QC confirmation.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for detection in detections:
        grouped.setdefault(str(detection["class_name"]), []).append(detection)
    return [
        {
            "defect_type": defect_type,
            "observation_count": len(items),
            "camera_ids": sorted({str(item["camera_id"]) for item in items}),
            "max_confidence": max(float(item["confidence"]) for item in items),
            "deduplication_status": (
                "CANDIDATE_DUPLICATE_REQUIRES_CALIBRATION"
                if len({str(item["camera_id"]) for item in items}) > 1
                else "SINGLE_VIEW"
            ),
        }
        for defect_type, items in grouped.items()
    ]
