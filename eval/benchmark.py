"""Reproducible benchmark for the current Visual QC rule engine.

The image archive does not contain machine-readable annotations.  Therefore its
file-name prefixes are reported as *data sources*, not treated as defect labels.
The decision benchmark uses explicit, reviewable ground-truth cases.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import zipfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from baseline_v0 import _rule_engine

LABELS = ("PASS", "FAIL", "REVIEW")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
KAGGLE_METRICS = (
    "metrics/precision(B)", "metrics/recall(B)", "metrics/mAP50(B)",
    "metrics/mAP50-95(B)", "metrics/precision(M)", "metrics/recall(M)",
    "metrics/mAP50(M)", "metrics/mAP50-95(M)",
)


@dataclass(frozen=True)
class Case:
    case_id: str
    category: str
    expected: str
    image_quality: int
    detections: tuple[dict[str, Any], ...] = ()


def benchmark_cases() -> list[Case]:
    """Cases around every rule and threshold (quality=70, confidence=.8, size=2)."""
    def defect(confidence: float, size: float) -> tuple[dict[str, float], ...]:
        return ({"confidence": confidence, "size_mm": size},)

    return [
        Case("low-quality-clean", "low_image_quality", "REVIEW", 69),
        Case("low-quality-with-defect", "low_image_quality", "REVIEW", 20, defect(.99, 9)),
        Case("quality-boundary-clean", "clean_surface", "PASS", 70),
        Case("high-quality-clean", "clean_surface", "PASS", 100),
        Case("clear-defect", "clear_defect", "FAIL", 90, defect(.95, 4)),
        Case("exact-fail-boundary", "clear_defect", "FAIL", 70, defect(.8, 2)),
        Case("confidence-below-boundary", "borderline_defect", "REVIEW", 90, defect(.79, 4)),
        Case("size-below-boundary", "borderline_defect", "REVIEW", 90, defect(.95, 1.99)),
        Case(
            "split-evidence-across-detections",
            "borderline_defect",
            "REVIEW",
            90,
            ({"confidence": .95, "size_mm": 1}, {"confidence": .6, "size_mm": 4}),
        ),
    ]


def manual_test_cases() -> list[Case]:
    """Five representative user-facing scenarios for evaluation evidence."""
    return [
        Case("MANUAL-01", "clean_surface", "PASS", 95),
        Case(
            "MANUAL-02",
            "clear_defect",
            "FAIL",
            92,
            ({"type": "scratch", "confidence": 0.94, "size_mm": 4.2},),
        ),
        Case(
            "MANUAL-03",
            "borderline_defect",
            "REVIEW",
            88,
            ({"type": "dent", "confidence": 0.72, "size_mm": 3.1},),
        ),
        Case("MANUAL-04", "low_image_quality", "REVIEW", 55),
        Case(
            "MANUAL-05",
            "multiple_defects",
            "FAIL",
            90,
            (
                {"type": "scratch", "confidence": 0.91, "size_mm": 3.5},
                {"type": "paint_damage", "confidence": 0.86, "size_mm": 2.4},
            ),
        ),
    ]


def run_manual_tests() -> dict[str, Any]:
    """Execute manual-use scenarios and retain the rule engine's actual output."""
    tests = []
    for case in manual_test_cases():
        test_input = {
            "image_quality": case.image_quality,
            "detections": list(case.detections),
        }
        started = time.perf_counter()
        actual_output = _rule_engine(test_input)
        latency_ms = (time.perf_counter() - started) * 1000
        tests.append(
            {
                "test_id": case.case_id,
                "scenario": case.category,
                "input": test_input,
                "expected_status": case.expected,
                "actual_output": actual_output,
                "latency_ms": round(latency_ms, 4),
                "result": "PASS" if actual_output["status"] == case.expected else "FAIL",
            }
        )
    passed = sum(test["result"] == "PASS" for test in tests)
    return {"summary": {"total": len(tests), "passed": passed, "failed": len(tests) - passed}, "tests": tests}


def manual_test_markdown(result: dict[str, Any]) -> str:
    """Render standalone evaluation evidence for manual-use scenarios."""
    summary = result["summary"]
    lines = [
        "# Manual Test Use Evidence",
        "",
        "> Actual outputs below were produced by the current deterministic rule engine. "
        "Detections are controlled test inputs, not predictions from a trained image model.",
        "",
        f"- Total tests: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        "",
    ]
    for test in result["tests"]:
        lines.extend(
            [
                f"## {test['test_id']} - {test['scenario']}",
                "",
                f"- Expected status: **{test['expected_status']}**",
                f"- Actual status: **{test['actual_output']['status']}**",
                f"- Test result: **{test['result']}**",
                f"- Latency: {test['latency_ms']:.4f} ms",
                "- Input:",
                "```json",
                json.dumps(test["input"], ensure_ascii=False, indent=2),
                "```",
                "- Actual output:",
                "```json",
                json.dumps(test["actual_output"], ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def benchmark_training_csv(path: Path) -> dict[str, Any]:
    """Summarize YOLO training metrics and select the strongest checkpoint."""
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = ("epoch", *KAGGLE_METRICS)
        missing = [column for column in required if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Missing required CSV columns: {', '.join(missing)}")
        rows = [{key: float(value) for key, value in row.items()} for row in reader]
    if not rows:
        raise ValueError("Training CSV contains no epochs")

    best_metrics = {}
    for metric in KAGGLE_METRICS:
        best = max(rows, key=lambda row: row[metric])
        best_metrics[metric] = {"value": round(best[metric], 5), "epoch": int(best["epoch"])}

    primary = "metrics/mAP50-95(B)"
    selected = max(rows, key=lambda row: row[primary])
    first, last = rows[0], rows[-1]
    return {
        "source": str(path),
        "epochs": len(rows),
        "selection_metric": primary,
        "recommended_epoch": int(selected["epoch"]),
        "recommended_checkpoint_metrics": {
            metric: round(selected[metric], 5) for metric in KAGGLE_METRICS
        },
        "best_metrics": best_metrics,
        "last_epoch": {
            "epoch": int(last["epoch"]),
            **{metric: round(last[metric], 5) for metric in KAGGLE_METRICS},
        },
        "improvement_from_first_epoch": {
            metric: round(last[metric] - first[metric], 5)
            for metric in ("metrics/mAP50-95(B)", "metrics/mAP50-95(M)")
        },
        "training_time_seconds": round(last.get("time", 0), 3),
        "interpretation": (
            "The model learned, but recall and mAP50-95 remain low for autonomous Visual QC. "
            "Use the same held-out split when comparing future runs."
        ),
    }


def training_benchmark_markdown(result: dict[str, Any]) -> str:
    """Render a standalone benchmark report from a YOLO results CSV."""
    labels = {
        "metrics/precision(B)": "Box precision", "metrics/recall(B)": "Box recall",
        "metrics/mAP50(B)": "Box mAP50", "metrics/mAP50-95(B)": "Box mAP50-95",
        "metrics/precision(M)": "Mask precision", "metrics/recall(M)": "Mask recall",
        "metrics/mAP50(M)": "Mask mAP50", "metrics/mAP50-95(M)": "Mask mAP50-95",
    }
    lines = [
        "# Kaggle Training Benchmark", "", f"- Source: `{result['source']}`",
        f"- Epochs: {result['epochs']}",
        f"- Recommended checkpoint: **epoch {result['recommended_epoch']}**",
        f"- Selection metric: `{result['selection_metric']}`",
        f"- Training time: {result['training_time_seconds'] / 3600:.2f} hours", "",
        "## Best result per metric", "", "| Metric | Best value | Epoch | Last epoch |",
        "|---|---:|---:|---:|",
    ]
    for metric in KAGGLE_METRICS:
        best = result["best_metrics"][metric]
        lines.append(
            f"| {labels[metric]} | {best['value']:.2%} | {best['epoch']} | "
            f"{result['last_epoch'][metric]:.2%} |"
        )
    lines.extend(["", "## Recommended checkpoint metrics", ""])
    for metric, value in result["recommended_checkpoint_metrics"].items():
        lines.append(f"- {labels[metric]}: {value:.2%}")
    lines.extend([
        "", "## Assessment", "", f"- {result['interpretation']}",
        "- Primary comparison metric for future models: `metrics/mAP50-95(B)`.",
        "- Safety metric for missed defects: `metrics/recall(B)`.",
        "- This CSV is validation history, not an independent test-set benchmark.", "",
    ])
    return "\n".join(lines)


def inventory_archive(path: Path) -> dict[str, Any]:
    sources: Counter[str] = Counter()
    extensions: Counter[str] = Counter()
    invalid_images: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            name = Path(item.filename).name
            suffix = Path(name).suffix.lower()
            if suffix not in IMAGE_SUFFIXES:
                invalid_images.append(item.filename)
                continue
            extensions[suffix] += 1
            match = re.match(r"^(cardd_train|car_damages|car_parts)_", name)
            sources[match.group(1) if match else "unknown"] += 1
    return {
        "archive": str(path),
        "image_count": sum(sources.values()),
        "source_counts": dict(sorted(sources.items())),
        "extension_counts": dict(sorted(extensions.items())),
        "non_image_count": len(invalid_images),
        "annotation_status": "missing",
        "warning": "Source prefixes are not defect ground-truth labels.",
    }


def _safe_div(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def run_cases(cases: Iterable[Case] | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    matrix = {actual: {predicted: 0 for predicted in LABELS} for actual in LABELS}
    for case in cases or benchmark_cases():
        payload = {"image_quality": case.image_quality, "detections": list(case.detections)}
        started = time.perf_counter()
        predicted = _rule_engine(payload)["status"]
        latencies.append((time.perf_counter() - started) * 1000)
        matrix[case.expected][predicted] += 1
        rows.append({**asdict(case), "predicted": predicted, "correct": predicted == case.expected})

    per_label = {}
    for label in LABELS:
        tp = matrix[label][label]
        fp = sum(matrix[actual][label] for actual in LABELS if actual != label)
        fn = sum(matrix[label][predicted] for predicted in LABELS if predicted != label)
        precision, recall = _safe_div(tp, tp + fp), _safe_div(tp, tp + fn)
        per_label[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_safe_div(2 * precision * recall, precision + recall), 4),
            "support": sum(matrix[label].values()),
        }

    category_rows: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        category_rows.setdefault(row["category"], []).append(row)
    category_accuracy = {
        name: round(sum(row["correct"] for row in items) / len(items), 4)
        for name, items in sorted(category_rows.items())
    }
    correct = sum(row["correct"] for row in rows)
    return {
        "summary": {
            "cases": len(rows),
            "correct": correct,
            "accuracy": round(_safe_div(correct, len(rows)), 4),
            "mean_latency_ms": round(sum(latencies) / len(latencies), 4) if latencies else 0,
            "max_latency_ms": round(max(latencies), 4) if latencies else 0,
        },
        "per_label": per_label,
        "per_category_accuracy": category_accuracy,
        "confusion_matrix": matrix,
        "failures": [row for row in rows if not row["correct"]],
        "cases": rows,
    }


def markdown_report(result: dict[str, Any]) -> str:
    summary, inventory = result["benchmark"]["summary"], result.get("dataset")
    lines = [
        "# Visual QC Benchmark Report",
        "",
        "## Rule-engine benchmark",
        "",
        f"- Cases: {summary['cases']}",
        f"- Accuracy: {summary['accuracy']:.2%}",
        f"- Mean latency: {summary['mean_latency_ms']:.4f} ms",
        f"- Wrong cases: {len(result['benchmark']['failures'])}",
        "",
        "| Label | Precision | Recall | F1 | Support |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, metrics in result["benchmark"]["per_label"].items():
        lines.append(
            f"| {label} | {metrics['precision']:.2%} | {metrics['recall']:.2%} | "
            f"{metrics['f1']:.2%} | {metrics['support']} |"
        )
    lines.extend(["", "## Accuracy by error scenario", ""])
    for category, accuracy in result["benchmark"]["per_category_accuracy"].items():
        lines.append(f"- `{category}`: {accuracy:.2%}")
    failures = result["benchmark"]["failures"]
    if failures:
        lines.extend(["", "## Failed scenarios", ""])
        for failure in failures:
            lines.append(
                f"- `{failure['case_id']}`: expected **{failure['expected']}**, "
                f"predicted **{failure['predicted']}**"
            )
    if inventory:
        lines.extend([
            "", "## Current dataset inventory", "",
            f"- Images: {inventory['image_count']}",
            f"- Sources: {json.dumps(inventory['source_counts'], ensure_ascii=False)}",
            f"- Annotation status: **{inventory['annotation_status']}**",
            f"- Note: {inventory['warning']}",
        ])
    lines.extend([
        "", "## Interpretation", "",
        "This measures the deterministic decision rules, not computer-vision defect detection. "
        "Detection metrics (mAP, IoU, per-defect recall) require an annotated validation split.", "",
        "## Reproduce", "",
        "```bash",
        "python -m eval.benchmark --archive train-20260810T025146Z-1-001.zip",
        "pytest tests/test_eval_benchmark.py -q",
        "```", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark the current Visual QC rules")
    parser.add_argument("--archive", type=Path, help="Optional image dataset ZIP")
    parser.add_argument(
        "--training-results",
        type=Path,
        default=Path("eval/results/results_kaggle.csv"),
        help="YOLO training results CSV",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("eval/results"))
    args = parser.parse_args()
    result: dict[str, Any] = {"benchmark": run_cases()}
    if args.archive:
        if not args.archive.is_file():
            parser.error(f"Archive not found: {args.archive}")
        result["dataset"] = inventory_archive(args.archive)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "benchmark.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "benchmark.md").write_text(markdown_report(result), encoding="utf-8")
    manual_result = run_manual_tests()
    (args.output_dir / "manual_test_evidence.json").write_text(
        json.dumps(manual_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "manual_test_evidence.md").write_text(
        manual_test_markdown(manual_result), encoding="utf-8"
    )
    if args.training_results.is_file():
        training_result = benchmark_training_csv(args.training_results)
        (args.output_dir / "kaggle_training_benchmark.json").write_text(
            json.dumps(training_result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (args.output_dir / "kaggle_training_benchmark.md").write_text(
            training_benchmark_markdown(training_result), encoding="utf-8"
        )
        print(
            f"Kaggle CSV: recommended epoch {training_result['recommended_epoch']} "
            f"({training_result['selection_metric']})"
        )
    print(markdown_report(result))
    print(
        f"Manual evidence: {manual_result['summary']['passed']}/"
        f"{manual_result['summary']['total']} tests passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
