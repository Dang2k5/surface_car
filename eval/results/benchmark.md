# Visual QC Benchmark Report

## Rule-engine benchmark

- Cases: 9
- Accuracy: 88.89%
- Mean latency: 0.0035 ms
- Wrong cases: 1

| Label | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| PASS | 100.00% | 100.00% | 100.00% | 2 |
| FAIL | 66.67% | 100.00% | 80.00% | 2 |
| REVIEW | 100.00% | 80.00% | 88.89% | 5 |

## Accuracy by error scenario

- `borderline_defect`: 66.67%
- `clean_surface`: 100.00%
- `clear_defect`: 100.00%
- `low_image_quality`: 100.00%

## Failed scenarios

- `split-evidence-across-detections`: expected **REVIEW**, predicted **FAIL**

## Current dataset inventory

- Images: 2983
- Sources: {"car_damages": 420, "car_parts": 528, "cardd_train": 2035}
- Annotation status: **missing**
- Note: Source prefixes are not defect ground-truth labels.

## Interpretation

This measures the deterministic decision rules, not computer-vision defect detection. Detection metrics (mAP, IoU, per-defect recall) require an annotated validation split.

## Reproduce

```bash
python -m eval.benchmark --archive train-20260810T025146Z-1-001.zip
pytest tests/test_eval_benchmark.py -q
```
