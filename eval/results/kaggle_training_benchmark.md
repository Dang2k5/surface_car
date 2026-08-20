# Kaggle Training Benchmark

- Source: `eval\results\results_kaggle.csv`
- Epochs: 40
- Recommended checkpoint: **epoch 39**
- Selection metric: `metrics/mAP50-95(B)`
- Training time: 2.05 hours

## Best result per metric

| Metric | Best value | Epoch | Last epoch |
|---|---:|---:|---:|
| Box precision | 65.60% | 20 | 32.27% |
| Box recall | 26.75% | 31 | 25.88% |
| Box mAP50 | 24.06% | 39 | 23.06% |
| Box mAP50-95 | 12.27% | 39 | 11.56% |
| Mask precision | 64.43% | 20 | 45.33% |
| Mask recall | 24.92% | 31 | 21.88% |
| Mask mAP50 | 23.00% | 39 | 21.82% |
| Mask mAP50-95 | 10.54% | 39 | 9.99% |

## Recommended checkpoint metrics

- Box precision: 37.27%
- Box recall: 24.75%
- Box mAP50: 24.06%
- Box mAP50-95: 12.27%
- Mask precision: 38.46%
- Mask recall: 23.27%
- Mask mAP50: 23.00%
- Mask mAP50-95: 10.54%

## Assessment

- The model learned, but recall and mAP50-95 remain low for autonomous Visual QC. Use the same held-out split when comparing future runs.
- Primary comparison metric for future models: `metrics/mAP50-95(B)`.
- Safety metric for missed defects: `metrics/recall(B)`.
- This CSV is validation history, not an independent test-set benchmark.
