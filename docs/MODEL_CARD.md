# Model Card — YOLO Segmentation (Visual QC Agent)

Tài liệu này mô tả **model artifact được runtime tiêu thụ để inference**
(`best.pt`), tách biệt khỏi dataset/training documentation
(`docs/DATASET.md`). Runtime repository này **không train model** — nó chỉ
nạp một artifact đã huấn luyện sẵn và chạy inference qua Ultralytics
(`agent/services/yolo_detector.py`, class `LocalYoloSegmentationDetector`).

```text
OFFLINE MODEL DEVELOPMENT (ngoài phạm vi runtime repo này)
  dataset (docs/DATASET.md) → training → validation → best.pt

RUNTIME SYSTEM (repo này)
  best.pt → Ultralytics YOLO.predict() → detection/segmentation → QCState
```

## Model summary

| Mục | Giá trị | Nguồn |
| --- | --- | --- |
| Model task | Instance segmentation (`model.task`, mặc định `"segment"`) | `agent/services/yolo_detector.py` |
| Model family | Ultralytics YOLO (segmentation variant) | `agent/services/yolo_detector.py` (`from ultralytics import YOLO`) |
| Model version | Cụ thể (YOLOv8-seg hay khác) | TODO — chưa xác định trong repo |
| Artifact path (mặc định) | `./data/best.pt` (`MODEL_PATH`) | `ENVIRONMENT.md` |
| Artifact identity | SHA-256 12 ký tự đầu, gán vào `model_version` mỗi lần load | `agent/services/yolo_detector.py::_sha256` |
| Classes (runtime taxonomy) | `dent`, `scratch` — các raw class name khác từ model bị lọc thành `unknown` và loại khỏi output | `agent/services/yolo_detector.py::CLASS_MAP` |
| Output per detection | `class_name`, `confidence`, `bbox` (xyxy), `segmentation` polygon (tối đa 128 điểm lấy mẫu) | `agent/services/yolo_detector.py` |

## Expected input / tested configuration

| Mục | Giá trị mặc định | Biến cấu hình |
| --- | --- | --- |
| Input | Ảnh JPEG/PNG từ trạm FNS (multi-camera hoặc single-camera) | `ENVIRONMENT.md` |
| Inference device | `cpu` (đổi sang CUDA device string khi có GPU) | `MODEL_DEVICE` |
| Confidence threshold | `0.25` | `MODEL_CONFIDENCE` |
| Inference image size | `640` (CPU demo); có thể tăng `1280` để ưu tiên độ chính xác — Ultralytics tự quy đổi bbox/mask về tọa độ ảnh nguồn | `MODEL_IMAGE_SIZE` |

Model không tự đo `depth_mm` hay kích thước vật lý; các giá trị mm chỉ xuất
hiện khi `FIXED_CAMERA_CALIBRATION_ENABLED=true` và luôn gắn trạng thái
`PILOT_FIXED_CAMERA_ESTIMATE_NOT_QC_APPROVED` (xem `ENVIRONMENT.md`,
`PRD.md` §7.2).

## Training location & dataset reference

- **Training location:** Offline/external — không thuộc runtime repo này.
- **Dataset reference:** `docs/DATASET.md` (hiện tại toàn bộ mục dataset source,
  số lượng ảnh, split, annotation policy đều ở trạng thái **TODO — chưa xác
  định**; không được suy đoán/bịa số liệu tại đây).
- **Validation metrics (mAP@0.5, v.v.):** TODO — chưa có kết quả validation
  chính thức được cung cấp trong repo. `PRD.md` §9 chỉ ghi **target** KPI
  (`mAP@0.5 ≥ 90%`), không phải kết quả đã đo.

## Target domain

Vehicle production / final visual QC tại trạm FNS (Finish Line) — kiểm tra
ngoại quan xe mới trước xuất xưởng. Không phù hợp với domain xe cũ đã va
chạm nặng hoặc ảnh sửa chữa hậu tai nạn (xem `docs/DATASET.md`).

## Known limitations

- Chỉ nhận diện 2 lớp `scratch`/`dent`; các class khác trong model (nếu có)
  bị lọc bỏ, không xuất hiện trong output runtime.
- Không cung cấp `depth_mm`, vật liệu, hoặc physical tolerance — các giá trị
  này phải đến từ depth sensor/QC measurement/MES-BOM (Future Extension,
  `PRD.md` §11), không phải từ model này.
- Chưa có model version string (ví dụ `yolov8n-seg`, `yolov8s-seg`) hay
  checksum/registry chính thức ngoài SHA-256 tự tính tại thời điểm load —
  cần Team 235 bổ sung khi chốt artifact chính thức cho production.
- Chưa có validation metrics đã xác minh (mAP, precision/recall theo lớp)
  gắn với artifact `best.pt` hiện tại.

## Model version / checksum

Runtime tự tính SHA-256 (12 ký tự đầu) của file `best.pt` tại thời điểm
load và gán vào `model_version` trong output (`agent/services/yolo_detector.py`).
Đây là cách theo dõi artifact identity hiện tại; chưa có model
registry/versioning chính thức ngoài cơ chế này.
