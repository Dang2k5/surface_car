# Manual Test Use Evidence

> Actual outputs below were produced by the current deterministic rule engine. Detections are controlled test inputs, not predictions from a trained image model.

- Total tests: 5
- Passed: 5
- Failed: 0

## MANUAL-01 - clean_surface

- Expected status: **PASS**
- Actual status: **PASS**
- Test result: **PASS**
- Latency: 0.0039 ms
- Input:
```json
{
  "image_quality": 95,
  "detections": []
}
```
- Actual output:
```json
{
  "status": "PASS",
  "reason": "Ảnh chất lượng 95% và không phát hiện lỗi nào.",
  "quality": 95
}
```

## MANUAL-02 - clear_defect

- Expected status: **FAIL**
- Actual status: **FAIL**
- Test result: **PASS**
- Latency: 0.0082 ms
- Input:
```json
{
  "image_quality": 92,
  "detections": [
    {
      "type": "scratch",
      "confidence": 0.94,
      "size_mm": 4.2
    }
  ]
}
```
- Actual output:
```json
{
  "status": "FAIL",
  "reason": "Phát hiện lỗi rõ ràng (Confidence=0.94, Size=4.20mm).",
  "quality": 92
}
```

## MANUAL-03 - borderline_defect

- Expected status: **REVIEW**
- Actual status: **REVIEW**
- Test result: **PASS**
- Latency: 0.0033 ms
- Input:
```json
{
  "image_quality": 88,
  "detections": [
    {
      "type": "dent",
      "confidence": 0.72,
      "size_mm": 3.1
    }
  ]
}
```
- Actual output:
```json
{
  "status": "REVIEW",
  "reason": "Lỗi nằm ở ranh giới nghi ngờ (Confidence=0.72, Size=3.10mm). Cần QC xác nhận.",
  "quality": 88
}
```

## MANUAL-04 - low_image_quality

- Expected status: **REVIEW**
- Actual status: **REVIEW**
- Test result: **PASS**
- Latency: 0.0011 ms
- Input:
```json
{
  "image_quality": 55,
  "detections": []
}
```
- Actual output:
```json
{
  "status": "REVIEW",
  "reason": "Ảnh chất lượng thấp (55%), cần QC kiểm tra thủ công.",
  "quality": 55
}
```

## MANUAL-05 - multiple_defects

- Expected status: **FAIL**
- Actual status: **FAIL**
- Test result: **PASS**
- Latency: 0.0032 ms
- Input:
```json
{
  "image_quality": 90,
  "detections": [
    {
      "type": "scratch",
      "confidence": 0.91,
      "size_mm": 3.5
    },
    {
      "type": "paint_damage",
      "confidence": 0.86,
      "size_mm": 2.4
    }
  ]
}
```
- Actual output:
```json
{
  "status": "FAIL",
  "reason": "Phát hiện lỗi rõ ràng (Confidence=0.91, Size=3.50mm).",
  "quality": 90
}
```
