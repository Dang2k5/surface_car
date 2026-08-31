"""Regression tests for VideoProcessor.extract_frames:

1. A video whose native frame rate is already coarser than the requested
   extract_interval (e.g. a 1fps timelapse-style camera with the minimum allowed
   0.5s interval) must not crash with ZeroDivisionError -- it should just yield
   every frame the camera actually has, not reject an otherwise-valid video.
2. Extracted frames must keep the camera's native resolution/aspect ratio -- no
   forced square resize -- so video and photo uploads feed the detector identically.
"""
from __future__ import annotations

import cv2
import numpy as np

from agent.services.video_processor import VideoProcessor


def _write_video(path, *, fps: float, frame_count: int, width: int = 320, height: int = 180):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    for i in range(frame_count):
        frame = np.full((height, width, 3), fill_value=i % 256, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_extract_frames_does_not_crash_on_low_fps_video(tmp_path):
    """fps=1.0 with the minimum allowed extract_interval=0.5s makes
    `fps * extract_interval == 0.5`, which truncated to int() is 0 -- the exact
    shape that used to raise ZeroDivisionError on `frame_idx % next_extract_frame`."""
    video_path = tmp_path / "low_fps.mp4"
    _write_video(video_path, fps=1.0, frame_count=6)

    processor = VideoProcessor(extract_interval=0.5, temp_dir=str(tmp_path))
    result = processor.extract_frames(video_path, camera_id="CAM-01")

    # native rate coarser than the requested interval -> every frame is kept
    assert result["extracted_frame_count"] == result["frame_count"]
    assert result["extracted_frame_count"] > 0


def test_extract_frames_keeps_native_resolution_no_forced_square_resize(tmp_path):
    video_path = tmp_path / "widescreen.mp4"
    _write_video(video_path, fps=10.0, frame_count=20, width=320, height=180)

    processor = VideoProcessor(extract_interval=0.5, temp_dir=str(tmp_path))
    result = processor.extract_frames(video_path, camera_id="CAM-01")

    assert result["extracted_frame_count"] > 0
    for frame in result["frames"]:
        height, width = frame["frame_data"].shape[:2]
        assert (width, height) == (320, 180)
