from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from agent.services.image_render import render_defect_images


def _write_png(path, size=(200, 150), color=(10, 20, 30)):
    Image.new("RGB", size, color).save(path, format="PNG")


def test_render_defect_images_from_bbox_only(tmp_path):
    image_path = tmp_path / "source.png"
    _write_png(image_path)
    detection = {
        "bbox": {"x1": 20.0, "y1": 15.0, "x2": 80.0, "y2": 70.0},
        "segmentation": None,
    }

    rendered = render_defect_images(image_path, detection)

    assert set(rendered) == {"overlay", "crop", "mask"}
    overlay = Image.open(BytesIO(rendered["overlay"]))
    assert overlay.size == (200, 150)
    crop = Image.open(BytesIO(rendered["crop"]))
    assert crop.size[0] > 0 and crop.size[1] > 0
    # Padded around the 60x55 bbox, but still smaller than the full frame.
    assert crop.size[0] < 200 and crop.size[1] < 150
    mask = Image.open(BytesIO(rendered["mask"]))
    assert mask.size == (200, 150)
    assert mask.mode == "L"
    assert mask.getpixel((50, 40)) == 255
    assert mask.getpixel((1, 1)) == 0


def test_render_defect_images_uses_segmentation_polygon_for_mask(tmp_path):
    image_path = tmp_path / "source.png"
    _write_png(image_path)
    detection = {
        "bbox": {"x1": 10.0, "y1": 10.0, "x2": 90.0, "y2": 90.0},
        "segmentation": {
            "format": "polygon",
            "points": [[20.0, 20.0], [80.0, 20.0], [80.0, 80.0], [20.0, 80.0]],
        },
    }

    rendered = render_defect_images(image_path, detection)
    mask = Image.open(BytesIO(rendered["mask"]))
    # Inside the polygon.
    assert mask.getpixel((50, 50)) == 255
    # Inside the bbox but outside the (smaller) polygon.
    assert mask.getpixel((15, 15)) == 0


def test_render_defect_images_clamps_bbox_that_exceeds_image_bounds(tmp_path):
    """A bbox reported against a different resolution than the current image
    must never invert the crop box or raise."""
    image_path = tmp_path / "tiny.png"
    _write_png(image_path, size=(1, 1))
    detection = {
        "bbox": {"x1": 220.0, "y1": 145.0, "x2": 405.0, "y2": 365.0},
        "segmentation": None,
    }

    rendered = render_defect_images(image_path, detection)
    crop = Image.open(BytesIO(rendered["crop"]))
    assert crop.size == (1, 1)


def test_render_defect_images_requires_a_bbox(tmp_path):
    image_path = tmp_path / "source.png"
    _write_png(image_path)

    with pytest.raises(ValueError):
        render_defect_images(image_path, {"bbox": None})
