from agent.services.defect_catalog import StaticDefectCatalog
from agent.services.reasoning import DeterministicReasoningService
from backend.app.database import Database


def test_seed_catalog_contains_ten_grouped_active_codes() -> None:
    database = Database(":memory:")
    try:
        codes = database.list_defect_codes()
        assert len(codes) == 10
        assert {item["defect_type"] for item in codes} == {"scratch", "dent"}
        assert all(item["defect_family"] for item in codes)
        assert all(item["classification_rule"] for item in codes)
    finally:
        database.close()


def test_classifier_selects_size_band_from_fixed_camera_estimate() -> None:
    catalog = StaticDefectCatalog()
    candidates = catalog.match("scratch")
    result = DeterministicReasoningService().classify_defect_code(
        {
            "defect_type": "scratch",
            "detections": [{"class_name": "scratch"}],
            "visual_measurements": {
                "estimated_width_mm": 92.0,
                "relative_position": "middle_center",
            },
            "bbox": {"x1": 0, "y1": 0, "x2": 115, "y2": 20},
        },
        candidates,
    )
    assert result.defect_code == "SCRATCH02"
    assert result.defect_family == "SURFACE_SCRATCH"
    assert result.similar_observation_warning is False


def test_classifier_warns_and_selects_cluster_code_for_similar_detections() -> None:
    catalog = StaticDefectCatalog()
    result = DeterministicReasoningService().classify_defect_code(
        {
            "defect_type": "dent",
            "detections": [{"class_name": "dent"}, {"class_name": "dent"}],
            "visual_measurements": {"estimated_width_mm": 40.0},
            "bbox": {"x1": 0, "y1": 0, "x2": 50, "y2": 50},
        },
        catalog.match("dent"),
    )
    assert result.defect_code == "DENT05"
    assert result.similar_observation_warning is True
