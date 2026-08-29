#!/usr/bin/env python3
"""Generate synthetic test videos for QC inspection testing.

Creates realistic-looking video sequences simulating product movement
through quality control checkpoints with simulated defects.
"""

import os
from pathlib import Path

import cv2
import numpy as np


def create_test_video(output_path: str | Path, camera_id: str = "CAM-01", duration_seconds: int = 5, fps: int = 30, defect_type: str = "dent"):
    """Create a test video with simulated product and defects.

    Args:
        output_path: Where to save video (e.g. "data/test_video_cam01.mp4")
        camera_id: Camera identifier for labeling
        duration_seconds: Video length in seconds
        fps: Frames per second
        defect_type: "dent", "scratch", or "none" for clean product
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    width, height = 640, 480
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    frames_count = duration_seconds * fps

    for frame_idx in range(frames_count):
        # Create white canvas
        frame = np.ones((height, width, 3), dtype=np.uint8) * 240

        # Draw background grid
        for i in range(0, width, 50):
            cv2.line(frame, (i, 0), (i, height), (200, 200, 200), 1)
        for i in range(0, height, 50):
            cv2.line(frame, (0, i), (width, i), (200, 200, 200), 1)

        # Simulate product moving left-to-right
        progress = frame_idx / frames_count  # 0.0 to 1.0
        product_x = int(progress * width * 1.2 - 100)
        product_y = height // 2

        # Draw product (rectangle)
        cv2.rectangle(frame, (product_x, product_y - 60), (product_x + 120, product_y + 60), (100, 150, 200), -1)
        cv2.rectangle(frame, (product_x, product_y - 60), (product_x + 120, product_y + 60), (50, 100, 150), 2)

        # Add simulated defects
        if defect_type == "dent" and 0.2 < progress < 0.8:
            # Dent in middle-left area of product
            cv2.circle(frame, (product_x + 30, product_y - 20), 12, (30, 50, 100), -1)
            cv2.circle(frame, (product_x + 30, product_y - 20), 12, (20, 40, 80), 2)

        elif defect_type == "scratch" and 0.3 < progress < 0.9:
            # Scratch across surface
            cv2.line(frame, (product_x + 20, product_y + 40), (product_x + 100, product_y + 45), (60, 60, 60), 3)

        # Camera label
        cv2.putText(
            frame,
            f"{camera_id} - Frame {frame_idx + 1}/{frames_count}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (50, 50, 50),
            2,
        )

        # Timestamp
        timestamp = frame_idx / fps
        cv2.putText(
            frame,
            f"Time: {timestamp:.2f}s",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (100, 100, 100),
            1,
        )

        # Defect indicator
        defect_label = defect_type.upper() if defect_type != "none" else "CLEAN"
        color = (0, 0, 255) if defect_type != "none" else (0, 255, 0)  # Red for defect, green for clean
        cv2.putText(
            frame,
            f"Status: {defect_label}",
            (width - 250, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
        )

        # Add frame number in corner
        cv2.putText(
            frame,
            str(frame_idx),
            (width - 60, height - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (150, 150, 150),
            2,
        )

        out.write(frame)

    out.release()
    print(f"✅ Created: {output_path} ({duration_seconds}s, {frames_count} frames, {defect_type})")


def main():
    """Generate test video set."""
    test_video_dir = Path("data/test_videos")
    test_video_dir.mkdir(parents=True, exist_ok=True)

    # Create video set with different defects
    print("Generating test videos for QC inspection...\n")

    # Single camera scenarios
    print("=== Single Camera Tests ===")
    create_test_video(
        test_video_dir / "cam01_clean_5s.mp4",
        camera_id="CAM-01",
        duration_seconds=5,
        defect_type="none"
    )
    create_test_video(
        test_video_dir / "cam01_dent_5s.mp4",
        camera_id="CAM-01",
        duration_seconds=5,
        defect_type="dent"
    )
    create_test_video(
        test_video_dir / "cam01_scratch_5s.mp4",
        camera_id="CAM-01",
        duration_seconds=5,
        defect_type="scratch"
    )

    # Multi-camera scenario (5 cameras, different perspectives)
    print("\n=== Multi-Camera Tests (5 cameras) ===")
    for cam_num in range(1, 6):
        create_test_video(
            test_video_dir / f"cam{cam_num:02d}_dent_5s.mp4",
            camera_id=f"CAM-{cam_num:02d}",
            duration_seconds=5,
            defect_type="dent" if cam_num <= 3 else "none"  # Defect in first 3 cameras
        )

    # Shorter videos for quick testing
    print("\n=== Quick Test Videos (2s) ===")
    create_test_video(
        test_video_dir / "quick_cam01_dent_2s.mp4",
        camera_id="CAM-01",
        duration_seconds=2,
        defect_type="dent"
    )

    print("\n✨ Test videos ready for local testing!")
    print(f"📁 Location: {test_video_dir}")
    print("\n📝 Usage:")
    print("  1. Upload any video from the test_videos folder")
    print("  2. API will extract frames every 1-2 seconds")
    print("  3. YOLO detection runs on each frame")
    print("  4. Defects aggregate (Tier 1 + Tier 2)")
    print("  5. Full inspection workflow executes")


if __name__ == "__main__":
    main()
