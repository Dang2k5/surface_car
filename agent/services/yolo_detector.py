from __future__ import annotations

import hashlib
import math
import time
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from agent.graph.state import QCState

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLASS_MAP = {
    "crack": "crack",
    "dent": "dent",
    "glass shatter": "glass_shatter",
    "lamp broken": "lamp_broken",
    "scratch": "scratch",
    "tire flat": "tire_flat",
}
SAFETY_PRIORITY = {
    "tire_flat": 60,
    "glass_shatter": 50,
    "lamp_broken": 40,
    "crack": 30,
    "dent": 20,
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


def _resolve_image_source(state: QCState) -> str:
    image_paths = state.get("image_paths") or []
    if image_paths:
        path = Path(image_paths[0])
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path.resolve())

    image_url = state.get("image_url", "")
    parsed = urlparse(image_url)
    url_path = parsed.path
    static_roots = {"/assets/uploads/": PROJECT_ROOT / "data" / "uploads"}
    for prefix, root in static_roots.items():
        if url_path.startswith(prefix):
            candidate = (root / url_path.removeprefix(prefix)).resolve()
            if not candidate.is_relative_to(root.resolve()):
                raise ValueError("Image path escapes the configured evidence directory")
            return str(candidate)
    if parsed.scheme in {"http", "https"}:
        return image_url
    raise ValueError(f"Unsupported image source: {image_url}")


class LocalYoloSegmentationDetector:
    """Ultralytics segmentation adapter that normalizes model output into QCState."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        device: str = "cpu",
        confidence: float = 0.25,
        image_size: int = 1280,
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
        self.model_version = _sha256(self.model_path)[:12]
        self.model = YOLO(str(self.model_path))
        self._lock = Lock()

    def detect(self, state: QCState) -> dict[str, Any]:
        source = _resolve_image_source(state)
        started = time.perf_counter()
        with self._lock:
            results = self.model.predict(
                source=source,
                conf=self.confidence,
                imgsz=self.image_size,
                device=self.device,
                verbose=False,
            )
        inference_ms = round((time.perf_counter() - started) * 1000, 1)
        if not results:
            raise RuntimeError("YOLO returned no Results object")

        result = results[0]
        height, width = (int(value) for value in result.orig_shape)
        detections: list[dict[str, Any]] = []
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
                polygon = _sample_polygon(polygons[index]) if index < len(polygons) else []
                detections.append(
                    {
                        "class_id": class_id,
                        "raw_class_name": raw_name,
                        "class_name": normalized_name,
                        "confidence": round(float(score), 6),
                        "bbox": {
                            "x1": round(float(xyxy[0]), 2),
                            "y1": round(float(xyxy[1]), 2),
                            "x2": round(float(xyxy[2]), 2),
                            "y2": round(float(xyxy[3]), 2),
                        },
                        "segmentation": {"format": "polygon", "points": polygon},
                    }
                )

        primary = max(
            detections,
            key=lambda item: (SAFETY_PRIORITY.get(item["class_name"], 0), item["confidence"]),
            default=None,
        )
        common = {
            "detections": detections,
            "image_width": width,
            "image_height": height,
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
            "severity": "UNASSESSED",
        }
