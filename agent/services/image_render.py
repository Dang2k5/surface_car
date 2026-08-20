"""Renders overlay/crop/mask PNGs from an existing YOLO detection (FR-17,
API_CONTRACT.md). This only visualizes YOLO's own bbox/mask output — it does
not introduce a new measurement, classification, or decision."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

_HIGHLIGHT_COLOR = (255, 40, 40)
_CROP_PADDING_RATIO = 0.15


def _polygon_points(detection: dict[str, Any]) -> list[tuple[float, float]] | None:
    segmentation = detection.get("segmentation") or {}
    points = segmentation.get("points")
    if not points or len(points) < 3:
        return None
    return [(float(x), float(y)) for x, y in points]


def _padded_bbox(bbox: dict[str, float], width: int, height: int) -> tuple[int, int, int, int]:
    box_width = bbox["x2"] - bbox["x1"]
    box_height = bbox["y2"] - bbox["y1"]
    pad_x = box_width * _CROP_PADDING_RATIO
    pad_y = box_height * _CROP_PADDING_RATIO
    # Clamp x1/y1 first so a bbox reported against a different source
    # resolution than the current image can never invert the crop box.
    x1 = min(max(0, int(bbox["x1"] - pad_x)), max(0, width - 1))
    y1 = min(max(0, int(bbox["y1"] - pad_y)), max(0, height - 1))
    x2 = max(x1 + 1, min(width, int(bbox["x2"] + pad_x)))
    y2 = max(y1 + 1, min(height, int(bbox["y2"] + pad_y)))
    return x1, y1, x2, y2


def _encode_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def render_defect_images(image_path: Path, detection: dict[str, Any]) -> dict[str, bytes]:
    """Return {"overlay", "crop", "mask"} PNG bytes for one detection's bbox/mask."""
    bbox = detection.get("bbox")
    if not bbox:
        raise ValueError("Detection has no bbox to render")
    polygon = _polygon_points(detection)

    with Image.open(image_path) as source:
        source = source.convert("RGB")
        width, height = source.size

        overlay = source.copy()
        draw = ImageDraw.Draw(overlay)
        outline_width = max(2, round(min(width, height) * 0.004))
        draw.rectangle(
            [(bbox["x1"], bbox["y1"]), (bbox["x2"], bbox["y2"])],
            outline=_HIGHLIGHT_COLOR,
            width=outline_width,
        )
        if polygon:
            draw.polygon(polygon, outline=_HIGHLIGHT_COLOR, width=outline_width)

        x1, y1, x2, y2 = _padded_bbox(bbox, width, height)
        crop = source.crop((x1, y1, x2, y2))

        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        if polygon:
            mask_draw.polygon(polygon, fill=255)
        else:
            mask_draw.rectangle([(bbox["x1"], bbox["y1"]), (bbox["x2"], bbox["y2"])], fill=255)

        return {
            "overlay": _encode_png(overlay),
            "crop": _encode_png(crop),
            "mask": _encode_png(mask),
        }


__all__: tuple[str, ...] = ("render_defect_images",)
