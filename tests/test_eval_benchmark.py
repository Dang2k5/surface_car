import zipfile
from pathlib import Path

from eval.benchmark import benchmark_training_csv, inventory_archive, run_cases, run_manual_tests


def test_current_rule_benchmark_has_full_scenario_coverage():
    result = run_cases()

    assert result["summary"]["cases"] == 9
    assert result["summary"]["accuracy"] == 0.8889
    assert set(result["per_category_accuracy"]) == {
        "borderline_defect", "clean_surface", "clear_defect", "low_image_quality"
    }
    assert [failure["case_id"] for failure in result["failures"]] == [
        "split-evidence-across-detections"
    ]
    assert result["confusion_matrix"]["REVIEW"]["FAIL"] == 1


def test_archive_prefixes_are_inventory_sources_not_labels(tmp_path: Path):
    archive = tmp_path / "images.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("train/cardd_train_001.jpg", b"image")
        output.writestr("train/car_damages_Car damages 1.png", b"image")
        output.writestr("train/readme.txt", b"notes")

    result = inventory_archive(archive)

    assert result["image_count"] == 2
    assert result["source_counts"] == {"car_damages": 1, "cardd_train": 1}
    assert result["non_image_count"] == 1
    assert result["annotation_status"] == "missing"


def test_manual_evidence_has_five_actual_rule_engine_outputs():
    result = run_manual_tests()

    assert result["summary"] == {"total": 5, "passed": 5, "failed": 0}
    assert [test["test_id"] for test in result["tests"]] == [
        "MANUAL-01",
        "MANUAL-02",
        "MANUAL-03",
        "MANUAL-04",
        "MANUAL-05",
    ]
    assert all("status" in test["actual_output"] for test in result["tests"])


def test_kaggle_training_csv_selects_best_strict_box_map():
    result = benchmark_training_csv(Path("eval/results/results_kaggle.csv"))

    assert result["epochs"] == 40
    assert result["recommended_epoch"] == 39
    assert result["best_metrics"]["metrics/mAP50-95(B)"] == {
        "value": 0.12268,
        "epoch": 39,
    }
    assert result["best_metrics"]["metrics/mAP50-95(M)"] == {
        "value": 0.10543,
        "epoch": 39,
    }
