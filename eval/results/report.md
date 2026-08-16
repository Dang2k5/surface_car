# Evaluation & Quality Report — Visual QC Agent (Team 235)

> Báo cáo kiểm định chất lượng mô hình Computer Vision (Scratch & Dent) và năng lực suy luận & phát hiện bất thường của LangGraph Agent theo tiêu chí BTC AI20K.

---

## 1. Core Metrics & Target Benchmarks

| Metric | Target (Mục tiêu) | Actual (Thực tế) | Tool / Method | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Computer Vision mAP@0.5 (Scratch & Dent)** | $\ge 90\%$ | — | YOLOv8 Val set | ⏳ |
| **Defect Localization & Depth Accuracy** | $\ge 92\%$ | — | So khớp tọa độ & ước lượng độ sâu | ⏳ |
| **Routing Decision Accuracy (Plan A vs B)** | $\ge 96\%$ | — | So khớp với Chuyên gia QC (Ground Truth) | ⏳ |
| **Systemic Anomaly Detection Recall** | $\ge 98\%$ | — | Bắt trọn chuỗi $\ge 3$ xe lỗi liên tiếp | ⏳ |
| **Line Stoppage Prevention Response Time** | $< 1.0\text{s}$ | — | Tốc độ kích hoạt điều phối làn đệm | ⏳ |
| **Total System Latency** | $< 2.0\text{ giây}$ | — | Benchmark API `POST /api/v1/inspect` | ⏳ |
| **Average Cost per Vehicle Inspection** | $\le \$0.004$ | — | Phoenix Token & Cost Tracking | ⏳ |
| **Unit Test Coverage** | $> 70\%$ | — | `pytest --cov=src` | ⏳ |

---

## 2. Test Datasets & Test Scenarios

### 2.1. Dataset Thử nghiệm
1. **MVTec Anomaly Detection (AD) + NEU Surface Defect Database:** Làm baseline kiểm thử nhận dạng vết xước kim loại, vết lõm biến dạng.
2. **Automotive Synthetic & Real Dataset (Team 235):**
   - 100 ảnh kiểm định bề mặt ô tô trạm FNS tập trung vào vết xước và móp cửa, nắp capo, mui xe.
   - **Tập dữ liệu Kiểm thử Bất thường Chuỗi (Time-Series Anomaly Test Set):** 20 chuỗi xe mô phỏng kịch bản nhà máy:
     - *Kịch bản 1:* 3 xe liên tiếp bị móp ở cửa trước trái do lỗi cối dập $\rightarrow$ Kỳ vọng: Agent phát hiện và kích hoạt điều phối làn đệm ngay tại xe thứ 3.
     - *Kịch bản 2:* Xe bị xước rải rác ngẫu nhiên $\rightarrow$ Kỳ vọng: Agent phân luồng Plan A bình thường, không phát báo động giả.

---

## 3. Automated Test Execution

### 3.1. Chạy Unit Tests
```bash
pytest tests/ -v
```

### 3.2. Chạy Benchmark Agent Reasoning & Anomaly Detection
```bash
python scripts/run_eval.py --dataset data/eval_ground_truth.json
```
