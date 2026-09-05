"""Video frame extraction and processing for multi-camera QC inspections.

Supports:
  - Multiple video formats (MP4, MOV, WebM, AVI, MKV, FLV)
  - Any resolution (auto-scales to model input size)
  - Configurable frame extraction interval (0.5-2 seconds)
  - Per-camera frame aggregation
  - Cross-camera defect deduplication
"""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import numpy as np


class VideoProcessingError(Exception):
    """Raised when video processing fails."""

    pass


class VideoProcessor:
    """Extract frames from video files with configurable sampling interval."""

    # Above this, a single upload's extracted frames would be buffered in memory and
    # then fed as one YOLO.predict() batch under the model's global lock (see
    # agent/services/yolo_detector.py), long enough to starve every other concurrent
    # inspection behind it. 180s at the minimum 0.5s interval is already 360 frames.
    MAX_VIDEO_DURATION_SECONDS = 180.0

    SUPPORTED_FORMATS = {
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".webm",
        ".flv",
        ".m4v",
        ".wmv",
        ".3gp",
    }
    SUPPORTED_MIMETYPES = {
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",
        "video/x-matroska",
        "video/webm",
        "video/x-flv",
        "video/mp4v-es",
        "video/x-ms-wmv",
        "video/3gpp",
    }

    @staticmethod
    def is_valid_video_format(filename: str, content_type: str | None = None) -> bool:
        """Check if file is a supported video format."""
        ext = Path(filename).suffix.lower()
        if ext in VideoProcessor.SUPPORTED_FORMATS:
            return True
        if content_type and content_type.lower() in VideoProcessor.SUPPORTED_MIMETYPES:
            return True
        return False

    def __init__(self, extract_interval: float = 1.0, temp_dir: str | None = None):
        """
        Args:
            extract_interval: Seconds between extracted frames (default 1.0)
            temp_dir: Temporary directory for video processing
        """
        if not (0.5 <= extract_interval <= 2.0):
            raise ValueError("extract_interval must be between 0.5 and 2.0 seconds")

        self.extract_interval = extract_interval
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def extract_frames(
        self,
        video_path: str | Path,
        camera_id: str = "unknown",
    ) -> dict[str, Any]:
        """
        Extract frames from video at specified interval, at the camera's native resolution
        (no resize here -- see the detector's own `imgsz` handling for that).

        Args:
            video_path: Path to video file
            camera_id: Camera identifier for tracking

        Returns:
            {
                "camera_id": str,
                "frames": [
                    {"timestamp": float, "frame_data": np.ndarray},
                    ...
                ],
                "duration_seconds": float,
                "fps": float,
                "resolution": (width, height),
                "frame_count": int,
                "extracted_frame_count": int,
                "video_sha256": str,
            }
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise VideoProcessingError(f"Video file not found: {video_path}")

        try:
            import cv2

            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                raise VideoProcessingError(f"Cannot open video file: {video_path}")

            try:
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

                if fps <= 0 or frame_count <= 0:
                    raise VideoProcessingError(
                        f"Invalid video: fps={fps}, frame_count={frame_count}"
                    )

                duration_seconds = frame_count / fps
                if duration_seconds > self.MAX_VIDEO_DURATION_SECONDS:
                    raise VideoProcessingError(
                        f"Video too long ({duration_seconds:.1f}s): max "
                        f"{self.MAX_VIDEO_DURATION_SECONDS:.0f}s per upload"
                    )

                # max(1, ...): when the native frame spacing (1/fps) is already coarser than
                # extract_interval (e.g. a 1.5fps timelapse camera with the minimum allowed
                # 0.5s interval), there is no frame to skip to sample any sparser than the
                # camera's own rate -- int(fps * interval) would be 0 there, causing a
                # ZeroDivisionError below. The correct behavior is to just take every frame
                # the camera actually has, not reject an otherwise-valid low-fps video.
                next_extract_frame = max(1, int(fps * self.extract_interval))

                # Extract frames
                extracted_frames = []
                frame_idx = 0

                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    if frame_idx % next_extract_frame == 0 or frame_idx == frame_count - 1:
                        timestamp = frame_idx / fps
                        # No resize here: keep the frame at the camera's native resolution and
                        # let LocalYoloSegmentationDetector.detect() resize it internally via
                        # `imgsz`, exactly like the photo-upload path does with the original
                        # image. Forcing a square resize here (as this used to do) distorted
                        # the aspect ratio before the model ever saw the frame -- something the
                        # photo path never did -- so the same physical defect could measure a
                        # different mm size (and therefore a different severity) depending on
                        # whether it was submitted as a photo or a video frame.
                        extracted_frames.append(
                            {"timestamp": round(timestamp, 3), "frame_data": frame}
                        )

                    frame_idx += 1

                # A single, real source of truth for "did we get anything": check the actual
                # extraction result instead of a separately-computed frame-count estimate (the
                # old `frames_to_extract = int(duration_seconds / self.extract_interval)` guard
                # used a different formula than the loop above and could diverge from it).
                if not extracted_frames:
                    raise VideoProcessingError(
                        f"No frames could be extracted from video (duration={duration_seconds:.2f}s, "
                        f"fps={fps:.2f}, frame_count={frame_count})"
                    )

                # Calculate video SHA256 for tracking
                video_sha256 = self._sha256_file(video_path)

                return {
                    "camera_id": camera_id,
                    "frames": extracted_frames,
                    "duration_seconds": round(duration_seconds, 2),
                    "fps": round(fps, 2),
                    "resolution": (width, height),
                    "frame_count": frame_count,
                    "extracted_frame_count": len(extracted_frames),
                    "video_sha256": video_sha256,
                }

            finally:
                cap.release()

        except ImportError as e:
            raise VideoProcessingError(
                "opencv-python (cv2) is required for video processing. "
                "Install with: pip install opencv-python"
            ) from e
        except Exception as e:
            raise VideoProcessingError(f"Error extracting frames: {str(e)}") from e

    @staticmethod
    def _sha256_file(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
        """Calculate SHA256 hash of file for integrity tracking."""
        sha256_hash = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()


class DefectDeduplicator:
    """
    Tier-1 aggregation: Deduplicate detections within a single camera's frames.

    Merges detections that appear across multiple frames of the same camera,
    treating them as the same physical defect if they are spatially close.
    """

    def __init__(
        self,
        spatial_threshold_px: int = 15,
        spatial_threshold_ratio: float = 0.02,
        iou_threshold: float = 0.25,
        temporal_threshold_sec: float = 1.5,
        confidence_weight: float = 0.7,
    ):
        """
        Args:
            spatial_threshold_px: Max pixel distance to merge detections when a detection is
                missing the normalized center ratio needed for spatial_threshold_ratio (legacy
                fallback only -- see _centers_close).
            spatial_threshold_ratio: Max center-to-center distance to merge detections,
                normalized to frame size (fraction of frame width/height, default 0.02 = 2%).
                Resolution-independent, unlike spatial_threshold_px: a 15px shift is a much
                bigger fraction of a 480p frame than a 4K one, so blur/motion on a low-res
                camera could fail a fixed-pixel check that a high-res camera would pass for the
                same physical defect, and vice versa.
            iou_threshold: Minimum bbox IOU (intersection over union) to merge two detections
                even when their centers drift apart -- blur often makes YOLO draw a
                differently-sized box for the same physical defect from one frame to the next,
                which can shift the center past the distance threshold while the boxes still
                overlap heavily. Either signal (close centers OR sufficient IOU) is enough.
            temporal_threshold_sec: Max time difference to merge detections (default 1.5s)
            confidence_weight: How much to weight confidence vs other factors
        """
        self.spatial_threshold_px = spatial_threshold_px
        self.spatial_threshold_ratio = spatial_threshold_ratio
        self.iou_threshold = iou_threshold
        self.temporal_threshold_sec = temporal_threshold_sec
        self.confidence_weight = confidence_weight

    def deduplicate_camera_detections(
        self, camera_id: str, detections_by_frame: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Deduplicate detections from multiple frames of same camera.

        Args:
            camera_id: Camera identifier
            detections_by_frame: List of detection batches from different frames
                Each element: {
                    "timestamp": float,
                    "detections": [detection_dict, ...]
                }

        Returns:
            {
                "camera_id": str,
                "unique_defects": [merged_detection, ...],
                "defect_count": int,
                "merge_info": {
                    "total_raw_detections": int,
                    "merged_into": int,
                    "merge_groups": [{...}, ...],
                }
            }
        """
        if not detections_by_frame:
            return {
                "camera_id": camera_id,
                "unique_defects": [],
                "defect_count": 0,
                "merge_info": {
                    "total_raw_detections": 0,
                    "merged_into": 0,
                    "merge_groups": [],
                },
            }

        # Flatten all detections with frame metadata
        all_detections = []
        for frame_data in detections_by_frame:
            timestamp = frame_data.get("timestamp", 0)
            for detection in frame_data.get("detections", []):
                detection_with_meta = dict(detection)
                detection_with_meta["_frame_timestamp"] = timestamp
                all_detections.append(detection_with_meta)

        if not all_detections:
            return {
                "camera_id": camera_id,
                "unique_defects": [],
                "defect_count": 0,
                "merge_info": {
                    "total_raw_detections": 0,
                    "merged_into": 0,
                    "merge_groups": [],
                },
            }

        # Merge detections
        merged = self._spatial_temporal_merge(all_detections)
        merge_groups = self._create_merge_groups(all_detections, merged)

        return {
            "camera_id": camera_id,
            "unique_defects": merged,
            "defect_count": len(merged),
            "merge_info": {
                "total_raw_detections": len(all_detections),
                "merged_into": len(merged),
                "merge_groups": merge_groups,
            },
        }

    def _spatial_temporal_merge(self, detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge detections using spatial and temporal proximity."""
        if not detections:
            return []

        # Sort by confidence (descending) to keep best detection as representative
        sorted_dets = sorted(detections, key=lambda d: d.get("confidence", 0), reverse=True)
        merged = []
        used_indices = set()

        for i, det_i in enumerate(sorted_dets):
            if i in used_indices:
                continue

            # Start a merge group with this detection
            merge_group = [i]
            used_indices.add(i)

            # Find similar detections
            for j, det_j in enumerate(sorted_dets[i + 1 :], start=i + 1):
                if j in used_indices:
                    continue

                if self._should_merge(det_i, det_j):
                    merge_group.append(j)
                    used_indices.add(j)

            # Create merged detection
            merged_det = self._merge_detection_group(
                [sorted_dets[idx] for idx in merge_group]
            )
            merged.append(merged_det)

        return merged

    def _should_merge(self, det_a: dict[str, Any], det_b: dict[str, Any]) -> bool:
        """Check if two detections should be merged."""
        # Must be same defect type
        if det_a.get("class_name") != det_b.get("class_name"):
            return False

        # Check temporal distance
        time_a = det_a.get("_frame_timestamp", 0)
        time_b = det_b.get("_frame_timestamp", 0)
        if abs(time_a - time_b) > self.temporal_threshold_sec:
            return False

        # Either signal is enough: centers still close together, OR the boxes overlap
        # heavily despite drifting apart (blur/motion commonly resizes the box for the same
        # physical defect from one frame to the next without moving its center much, or vice
        # versa -- requiring both would miss real matches that only satisfy one).
        return self._centers_close(det_a, det_b) or (
            self._iou(det_a.get("bbox"), det_b.get("bbox")) >= self.iou_threshold
        )

    def _centers_close(self, det_a: dict[str, Any], det_b: dict[str, Any]) -> bool:
        """Resolution-independent center distance check via each detection's own
        center_x_ratio/center_y_ratio (normalized 0-1, set by yolo_detector.py at detect time)
        when available, falling back to a raw pixel distance for callers that don't provide it."""
        measurements_a = det_a.get("visual_measurements") or {}
        measurements_b = det_b.get("visual_measurements") or {}
        ratio_a = (measurements_a.get("center_x_ratio"), measurements_a.get("center_y_ratio"))
        ratio_b = (measurements_b.get("center_x_ratio"), measurements_b.get("center_y_ratio"))
        if None not in ratio_a and None not in ratio_b:
            distance = math.hypot(ratio_a[0] - ratio_b[0], ratio_a[1] - ratio_b[1])
            return distance <= self.spatial_threshold_ratio

        bbox_a = det_a.get("bbox", {}) or {}
        bbox_b = det_b.get("bbox", {}) or {}
        center_a = (
            (bbox_a.get("x1", 0) + bbox_a.get("x2", 0)) / 2,
            (bbox_a.get("y1", 0) + bbox_a.get("y2", 0)) / 2,
        )
        center_b = (
            (bbox_b.get("x1", 0) + bbox_b.get("x2", 0)) / 2,
            (bbox_b.get("y1", 0) + bbox_b.get("y2", 0)) / 2,
        )
        distance = np.sqrt(
            (center_a[0] - center_b[0]) ** 2 + (center_a[1] - center_b[1]) ** 2
        )
        return distance <= self.spatial_threshold_px

    @staticmethod
    def _iou(bbox_a: dict[str, Any] | None, bbox_b: dict[str, Any] | None) -> float:
        """Intersection-over-union of two x1/y1/x2/y2 pixel bboxes, 0.0 if either is missing
        or they don't overlap."""
        if not bbox_a or not bbox_b:
            return 0.0
        ax1, ay1, ax2, ay2 = bbox_a.get("x1", 0), bbox_a.get("y1", 0), bbox_a.get("x2", 0), bbox_a.get("y2", 0)
        bx1, by1, bx2, by2 = bbox_b.get("x1", 0), bbox_b.get("y1", 0), bbox_b.get("x2", 0), bbox_b.get("y2", 0)

        inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
        inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
        inter_area = inter_w * inter_h
        if inter_area <= 0:
            return 0.0

        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - inter_area
        return inter_area / union if union > 0 else 0.0

    @staticmethod
    def _merge_detection_group(detections: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge a group of similar detections into one."""
        if not detections:
            return {}

        # Use highest confidence detection as base
        best = max(detections, key=lambda d: d.get("confidence", 0))

        # Average measurements from all detections. Copy first -- best's own
        # visual_measurements dict must not be mutated in place, since best is still one of
        # the caller's original per-frame detections and may be read again elsewhere.
        measurements = dict(best.get("visual_measurements") or {})
        if len(detections) > 1:
            measurement_keys = ["estimated_width_mm", "estimated_height_mm", "estimated_length_mm"]
            for key in measurement_keys:
                if key in measurements:
                    avg = sum(
                        d.get("visual_measurements", {}).get(key, 0) for d in detections
                    ) / len(detections)
                    measurements[key] = round(avg, 2)

        # Create merged detection
        merged = dict(best)
        merged["visual_measurements"] = measurements
        merged["_merge_count"] = len(detections)
        merged["_frame_timestamps"] = sorted(
            set(d.get("_frame_timestamp", 0) for d in detections)
        )
        # Keep EVERY observation's own bbox/segmentation, not just the single "best" frame's —
        # each raw detection here was already independently inferred by YOLO on its own frame
        # (no extra inference cost to keep this), so the player can draw the exact box/mask for
        # whichever frame is nearest the video's current playback time instead of freezing the
        # mask at the position it happened to have in the highest-confidence frame alone.
        merged["_track_frames"] = sorted(
            (
                {
                    "timestamp": d.get("_frame_timestamp", 0),
                    "bbox": d.get("bbox"),
                    "segmentation": d.get("segmentation"),
                }
                for d in detections
            ),
            key=lambda f: f["timestamp"],
        )

        return merged

    @staticmethod
    def _create_merge_groups(
        originals: list[dict[str, Any]], merged: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Create tracking info for merged groups (for debugging)."""
        groups = []
        for merged_det in merged:
            merge_count = merged_det.get("_merge_count", 1)
            if merge_count > 1:
                groups.append(
                    {
                        "merged_detection_id": merged_det.get("detection_id", "unknown"),
                        "detection_type": merged_det.get("class_name", "unknown"),
                        "original_count": merge_count,
                        "frame_count": len(merged_det.get("_frame_timestamps", [])),
                    }
                )

        return groups


__all__ = (
    "VideoProcessor",
    "DefectDeduplicator",
    "VideoProcessingError",
)
