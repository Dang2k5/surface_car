# API Contract & Data Schemas
# Visual QC Agent (Team 235) — Automotive FNS Station

Tài liệu quy chuẩn giao tiếp (Data Contracts) giữa:
1. **YOLO Segmentation (Vision Engine: Scratch & Dent Detection)**
2. **Geometry Processor (Deterministic Geometry Extraction)**
3. **LangGraph Agent (Industrial Domain Reasoning & Anomaly Engine)**
4. **Backend API (FastAPI Gateway) + S3/MinIO Object Storage + PostgreSQL/Supabase**
5. **Workstation UI (Next.js Touch Dashboard)**

Xem `PRD.md` §2 cho sơ đồ kiến trúc tổng thể và `POLICY_GOVERNANCE.md` cho ranh
giới thẩm quyền của từng thành phần. Mỗi nhóm field dưới đây ghi rõ provenance
(`source = yolo | geometry_processor | camera_calibration |
depth_sensor | human_qc | qc_policy`).

---

## 1. YOLO Segmentation Output Schema (`VisionDetectionResult`)

Mô hình YOLO Segmentation tập trung nhận diện chuyên sâu 2 loại khuyết tật bề mặt: `scratch` (vết xước) và `dent` (vết lõm/móp). Đây là nguồn duy nhất (`source = yolo`) cho `type`, `confidence`, `bounding_box`, `mask`/`polygon`.

```json
{
  "inspection_id": "INSP-20260816-001",
  "vehicle_id": "CAR-20260816-001",
  "lot_id": "LOT-20260816-A",
  "shift_id": "SHIFT-A",
  "production_date": "2026-08-16",
  "station_id": "QC-01",
  "timestamp": "2026-08-16T12:00:00Z",
  "camera_id": "CAM_FNS_DOOR_LH",
  "vehicle_model": "SUV_EV",
  "original_image_key": "inspections/INSP-20260816-001/original.jpg",
  "defects": [
    {
      "defect_id": "DEF-001",
      "type": "dent",
      "confidence": 0.95,
      "bounding_box": {
        "x_min": 450,
        "y_min": 320,
        "x_max": 580,
        "y_max": 410
      },
      "polygon": [],
      "mask_image_key": "inspections/INSP-20260816-001/masks/DEF-001.png",
      "estimated_depth_mm": null,
      "surface_area_mm2": null,
      "physical_measurement_status": "REQUIRES_CALIBRATION_OR_QC_MEASUREMENT",
      "zone_name": "door_front_left_class_a"
    }
  ]
}
```

`lot_id`, `shift_id`, `production_date`, `station_id` hỗ trợ Historical Trend
theo lot/shift (`PRD.md` §6.3); chúng không thay thế `vehicle_id`, vẫn là
identifier bắt buộc của từng xe.

---

## 2. Geometry Processor Output Schema (`GeometryResult`)

Được tính deterministic bằng OpenCV/NumPy từ mask/polygon của YOLO (`source =
geometry_processor`). Multimodal LLM không được dùng để tính các giá trị này.

```json
{
  "defect_id": "DEF-001",
  "area_px": 5200,
  "bbox_width_px": 130,
  "bbox_height_px": 90,
  "centroid": [575, 255],
  "orientation_deg": 4.7,
  "aspect_ratio": 1.44,
  "perimeter_px": 410,
  "mm_conversion": {
    "available": true,
    "calibration_profile_id": "FNS_FRONT_PILOT_1280",
    "surface_area_mm2": null,
    "physical_measurement_status": "PILOT_FIXED_CAMERA_ESTIMATE_NOT_QC_APPROVED"
  }
}
```

`mm_conversion` chỉ được tạo khi `FIXED_CAMERA_CALIBRATION_ENABLED=true`
(`ENVIRONMENT.md`); nếu không có calibration hợp lệ, `mm_conversion.available =
false` và không có giá trị mm nào được suy diễn.

---

## 3. LangGraph Agent State Schema (`QCState`)

Được định nghĩa tại `agent/graph/state.py`. Schema quản lý cả luồng phán quyết xe đơn lẻ lẫn cơ chế phát hiện bất thường lặp lại (Systemic Anomaly). Node graph chuẩn hóa: `ingest → detect → extract_geometry → classify → decide → decision_gate → (final_decide | HITL → human_review → [supervisor_review] → resume → final_decide) → explain → complete → update_trend` (trục chính `detect → classify → decide → HITL`). `explain` luôn chạy sau final decision, không bao giờ trước HITL, vì kết luận có thể đổi sau khi QC xác nhận/override — xem `POLICY_GOVERNANCE.md`. Trạng thái triển khai runtime tại `AGENT_FLOW.md`.

```python
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

class GeometryFeatures(BaseModel):
    # source = geometry_processor — deterministic OpenCV/NumPy, không dùng LLM
    area_px: Optional[float] = None
    bbox_width_px: Optional[float] = None
    bbox_height_px: Optional[float] = None
    centroid: Optional[List[float]] = None
    orientation_deg: Optional[float] = None
    aspect_ratio: Optional[float] = None
    perimeter_px: Optional[float] = None

class DefectItem(BaseModel):
    defect_id: str
    type: Literal["dent", "scratch"]
    confidence: float  # source = yolo
    bbox: List[int]  # [xmin, ymin, xmax, ymax] — source = yolo
    mask_image_key: Optional[str] = None
    crop_image_key: Optional[str] = None
    geometry: Optional[GeometryFeatures] = None
    # Chỉ có giá trị khi camera đã calibration/depth-enabled hoặc QC đo xác nhận.
    estimated_depth_mm: Optional[float] = None
    surface_area_mm2: Optional[float] = None
    physical_measurement_status: str = "REQUIRES_CALIBRATION_OR_QC_MEASUREMENT"
    zone_name: str
    gdt_group: Optional[Literal["Group 1", "Group 2", "Group 3", "Group 4", "Group 5"]] = None
    gdt_tolerance_allowed_mm: Optional[float] = None  # DEMO_BASELINE_ONLY, xem PRD.md §5.1
    severity_rank: Optional[Literal["P", "S", "A", "B", "C", "D"]] = None
    is_exceeding_tolerance: Optional[bool] = None

class SystemicAnomalyAlert(BaseModel):
    is_anomaly_detected: bool = False
    consecutive_defect_count: int = 0
    repetitive_zone: Optional[str] = None
    repetitive_defect_type: Optional[Literal["dent", "scratch"]] = None
    predicted_root_cause: Optional[str] = None  # Hypothesis, cần QC xác minh — không phải kết luận tự động
    upstream_target_shop: Optional[str] = None  # Ví dụ: "Stamping Shop Line 1"
    line_stoppage_risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"
    actionable_routing_command: Optional[str] = None # "Reroute batch to Offline Buffer Area"

class QCState(TypedDict):
    inspection_id: str
    thread_id: str
    vehicle_id: str
    vehicle_model: str
    lot_id: Optional[str]
    shift_id: Optional[str]
    production_date: Optional[str]
    station_id: str
    image_url: str
    original_image_key: str
    overlay_image_key: Optional[str]
    camera_id: str
    zone_name: str
    detections: List[Dict[str, Any]]  # source = yolo
    enriched_defects: List[DefectItem]  # detections + geometry + operational metadata
    # Một entry cho mỗi DETECTION (không phải mỗi camera — một camera có thể có
    # nhiều finding độc lập) — mỗi detection được phân loại defect_code độc lập bằng
    # rule engine deterministic (agent/services/defect_rule_engine.py, KHÔNG dùng
    # LLM — xem PRD.md FR-03e), không suy diễn từ detection/camera khác.
    camera_classifications: List[Dict[str, Any]]
    # camera_id của các camera có phát hiện nhưng chưa phân loại được defect_code
    # (rule engine không tự động khớp được, hoặc mã được đánh dấu REQUIRES_HUMAN).
    # Không còn tự nó ép HITL: một finding CONFIRMED FAIL với confidence đủ cao ở
    # camera khác vẫn chốt FAIL ngay; unresolved_camera_ids chỉ ép HITL khi KHÔNG
    # có FAIL nào đủ tin cậy để tự quyết (xem confidence gate ở mục "Quy ước tên
    # trường" bên dưới).
    unresolved_camera_ids: List[str]
    # PolicyDecision (mục 3, agent/services/policy.py) cho từng camera đã phân
    # loại — final_status tổng hợp theo nguyên tắc FAIL-wins trên tập finding đủ
    # tin cậy (confidence ≥ CONFIRMED_THRESHOLD): bất kỳ camera nào FAIL thì cả
    # inspection FAIL, bất kể camera khác PASS hoặc còn finding mơ hồ khác.
    camera_policy_decisions: List[Dict[str, Any]]
    # Mọi mặt xe (front/rear/left/right/top) có phát hiện lỗi trong CHÍNH inspection
    # này — một inspection gộp cả 5 camera cố định nên có thể ảnh hưởng nhiều mặt
    # cùng lúc; zone_name chỉ ghi MỘT mặt (mặt của lỗi nặng nhất).
    affected_zones: List[str]
    suggested_defect_codes: List[Dict[str, Any]]
    classified_defect_code: Optional[str]
    defect_family: Optional[str]
    defect_code_classification: Dict[str, Any]
    similar_defect_warning: bool
    agent_analysis: Dict[str, Any]

    # 1. Phán quyết Xe Đơn lẻ (Individual Vehicle Decision)
    severity: Literal["P", "S", "A", "B", "C", "D", "NONE", "UNASSESSED"]
    recommendation_code: str  # action_code từ QC Rules, vd RELEASE_TO_NEXT_QUALITY_GATE
    recommendation: str
    allow_test_drive: bool
    decision: str  # mã trạng thái nội bộ ở bước assessment, KHÔNG phải business decision cuối
    reason: str
    final_status: str  # business decision chuẩn, chỉ hai giá trị: PASS | FAIL

    # 2. Cảnh báo Bất thường Chuỗi & Chống Dừng Line (Systemic Anomaly, realtime sliding window)
    anomaly_alert: Optional[SystemicAnomalyAlert]

    # 3. Human-In-The-Loop
    hitl_status: Literal["PENDING", "CONFIRMED", "OVERRIDDEN", "SUPERVISOR_APPROVED", "SUPERVISOR_REJECTED"]
    human_required: bool
    human_decision: Optional[Dict[str, Any]]

    # 4. RBAC / audit
    requested_by_role: Optional[Literal["QC_OPERATOR", "QC_SUPERVISOR"]]
    reviewed_by_role: Optional[Literal["QC_OPERATOR", "QC_SUPERVISOR"]]
```

### Quy ước tên trường

- `vehicle_id`: mã kỹ thuật bắt buộc để theo dõi một xe/phiên trong hệ thống.
- `lot_id`, `shift_id`, `production_date`, `station_id`: metadata nghiệp vụ cho Historical Trend (`PRD.md` §6.3); `lot_id`/`shift_id` là tùy chọn ở các luồng chưa gắn lô/ca.
- `zone_name`: vùng kiểm tra tương đối hoặc khu vực camera quan sát.
- `detections`: output đã chuẩn hóa trực tiếp từ YOLO; `enriched_defects`: cùng finding sau khi Agent bổ sung `geometry` (Geometry Processor), zone và metadata vận hành. Mỗi item giữ nguyên toàn bộ finding từ mọi camera (không chỉ lỗi nặng nhất) — mỗi item có `detection_id` (`{camera_id}::{index}`) và `is_primary`; `state.primary_detection_id` chỉ còn dùng để chọn finding dẫn dắt narrative của reasoning LLM, **không còn quyết định policy**. Từ khi tách policy theo từng camera, `assess_result` (`agent/graph/nodes.py`) phân loại `defect_code` độc lập cho MỖI camera có phát hiện (`camera_classifications`) và gọi `PolicyCatalog.evaluate()` riêng cho từng camera đã phân loại (`camera_policy_decisions`, ghi cả những camera chưa đủ tin cậy — audit trail đầy đủ) — mỗi finding có `severity_rank` thật của camera đó (không còn nhãn `UNCLASSIFIED_SECONDARY_FINDING` mặc định cho finding không phải primary).
  - **Confidence gate (`CONFIRMED_THRESHOLD`, mặc định `0.85`, `ENVIRONMENT.md`):** một finding chỉ được coi là "đáng tin" (confident) khi vừa khớp `defect_catalog` (`catalog_defect_type` khác null) **vừa** có YOLO `confidence ≥ CONFIRMED_THRESHOLD`. Finding dưới ngưỡng này — dù đã khớp danh mục — vẫn bị coi là mơ hồ (ambiguous), y hệt một camera chưa khớp được danh mục (`unresolved_camera_ids`).
  - **Tổng hợp PASS/FAIL/HITL:** nếu có **ít nhất một** finding confident bị policy xác nhận `FAIL` → cả inspection `FAIL` ngay (worst-wins trên tập finding confident), **không cần chờ** các finding mơ hồ khác được giải quyết. Chỉ khi **không có** FAIL confident nào mà vẫn còn finding mơ hồ (`unresolved_camera_ids` non-empty hoặc dưới ngưỡng confidence) thì mới route sang HITL. Xe chỉ `PASS` khi mọi finding confident đều được policy đánh giá `PASS` và không còn finding mơ hồ nào.
- `affected_zones`: danh sách tất cả mặt xe (front/rear/left/right/top — 5 camera cố định mỗi camera 1 mặt) có lỗi trong inspection hiện tại; dùng cho mọi nơi hiển thị tổng hợp cả inspection (vd cột "Vùng lỗi" ở màn hình tra cứu). `zone_name` vẫn giữ nguyên nghĩa cũ — một giá trị duy nhất (mặt của lỗi nặng nhất) — cho các ngữ cảnh chỉ có một vùng thật sự (một detection, hoặc một cụm cảnh báo Early Warning ở `backend/app/quality_alerts.py`).
- `severity` là mức độ tổng thể duy nhất; không tạo thêm alias `overall_severity_rank`.
- `recommendation_code`: mã hành động chuẩn duy nhất trong `QCState`; `recommendation` là mô tả dễ đọc.
- `recommended_plan` chỉ tồn tại ở response `/api/v1/inspect` để tương thích client cũ. `final_action` không còn thuộc contract.
- **`decision` vs `final_status` — không được dùng lẫn nhau:** `decision` là mã trạng thái nội bộ do node `assess_result`/`human_review`/`supervisor_review` sinh ra để mô tả *vì sao* graph chọn nhánh này (ví dụ `DEFECT_CONFIRMED`, `LOW_CONFIDENCE_OR_UNCLASSIFIED_REVIEW_REQUIRED` — finding dưới `CONFIRMED_THRESHOLD` hoặc chưa khớp danh mục và không có FAIL confident nào khác chốt được kết quả, `MANUAL_REINSPECTION_REQUIRED` — mọi finding đều confident nhưng không policy `APPROVED` nào khớp, `MODEL_ERROR_REVIEW_REQUIRED`, `MANDATORY_REVIEW_LINE_ALERT`, `DEFECT_REJECTED_BY_QC`, `OVERRIDE_REJECTED_BY_SUPERVISOR`) — đây là lý do vận hành/chẩn đoán, không phải phán quyết QC cuối cùng. `LLM_AGENT_UNAVAILABLE` từng là một giá trị `decision` (ép route sang HITL khi LLM giải trình lỗi) nhưng **đã bị loại bỏ** kể từ bản sửa root-cause ngày 2026-08-31 — LLM giải trình lỗi giờ không còn đổi `decision`/route nữa, chỉ hạ cấp `agent_reasoning_status` xuống `LLM_UNAVAILABLE_FALLBACK_DETERMINISTIC` (xem `ISSUE_REMEDIATION_PLAN.md` mục 1). **`final_status` mới là business decision chuẩn** hiển thị cho QC và đối chiếu với đề bài (PASS/FAIL/cần người kiểm — mục 5.3 `PRD.md`), do QC Rules (`agent/services/policy.py` + `agent/policies/qc_policy_catalog.json`) quyết định; **chỉ hai giá trị**: `PASS` (release, cho phép chạy thử) hoặc `FAIL` (giữ xe, chuyển Rework). Không còn phân biệt `HOLD_FOR_QC`/`HOLD_FOR_REWORK`/`HUMAN_OVERRIDE_APPLIED` — mọi FAIL, dù tự động hay qua HITL/override, đều là cùng một giá trị `FAIL`. UI chỉ hiển thị `final_status`, không hiển thị `decision` thô cho QC (xem `UI_WORKFLOWS.md`).
- `hitl_status` có 5 giá trị: `PENDING` (đang chờ `human_review`), `CONFIRMED` (không cần HITL, hoặc Inspector đã PASS/FAIL), `OVERRIDDEN` (Inspector chuyển cấp, đang chờ `supervisor_review`), `SUPERVISOR_APPROVED`/`SUPERVISOR_REJECTED` (Supervisor đã xử lý case chuyển cấp). Không có trạng thái `NOT_REQUIRED` riêng — khi HITL không cần thiết, `hitl_status` được gán thẳng `CONFIRMED`.
- `original_image_key`/`overlay_image_key`/`mask_image_key`/`crop_image_key`: S3/MinIO object key, không phải binary; xem mục 4.

---

## 4. Object Storage (S3/MinIO) Layout

Ảnh/mask/crop không lưu binary trong PostgreSQL. Cấu trúc key:

```text
inspections/
  INSP-001/
    original.jpg
    overlay.jpg
    defects/
      DEF-001.jpg
    masks/
      DEF-001.png
```

Database (PostgreSQL/Supabase) chỉ lưu metadata/key: `original_image_key`,
`overlay_image_key`, `crop_image_key`, `mask_image_key`. Frontend truy cập ảnh
qua backend proxy hoặc presigned URL — không truy cập bucket trực tiếp bằng
secret key. Xem `ENVIRONMENT.md` cho biến cấu hình `S3_*`/`OBJECT_STORAGE_*`.

---

## 5. Tool Interfaces & Domain Engines

### Tool 1: `lookup_gdt_standard(zone_name: str, vehicle_model: str)`
- **Input:** `zone_name` (ví dụ: `"door_front_left_class_a"`), `vehicle_model` (`"SUV_EV"`)
- **Output** (giá trị `DEMO_BASELINE_ONLY`, xem `PRD.md` §5.1):
  ```json
  {
    "zone_name": "door_front_left_class_a",
    "gdt_group": "Group 1",
    "surface_class": "Class A",
    "max_tolerance_mm": 0.7,
    "tolerance_status": "DEMO_BASELINE_ONLY",
    "inspection_rule": "Vết móp > 0.7mm hoặc xước sâu chạm kim loại cấm cho chạy thử."
  }
  ```

### Tool 2: `analyze_defect_trend_anomaly(current_defects: list, window_size: int = 10)`
- **Input:** Danh sách khuyết tật của xe hiện tại + Cửa sổ $N$ xe gần nhất trong ca (Sliding Window realtime — `PRD.md` §6.1).
- **Output:**
  ```json
  {
    "is_anomaly_detected": true,
    "consecutive_defect_count": 3,
    "repetitive_zone": "door_front_left_class_a",
    "repetitive_defect_type": "dent",
    "predicted_root_cause": "Phát hiện 3 xe liên tiếp cùng bị móp tại tọa độ mép cửa trước trái. Khả năng cao khuôn dập tại Xưởng Dập bị dính mạt kim loại hoặc tay gắp robot hàn kẹp sai lực.",
    "root_cause_evidence": "COORDINATE_CLUSTER_CONFIRMED",
    "root_cause_evidence_detail": {
      "coordinate_cluster": true,
      "single_camera": true,
      "severity_at_least_warning": true,
      "occurrence_count": 3
    },
    "upstream_target_shop": "Stamping Shop / Framing Robot 04",
    "line_stoppage_risk": "HIGH",
    "action_plan": "1. Gửi cảnh báo khẩn đến Trưởng ca Xưởng Dập. 2. Đề xuất điều hướng các xe lỗi vào Vùng đệm Offline để tránh dừng Line FNS chính (Trưởng ca xác nhận và thực thi thao tác điều hướng)."
  }
  ```

### Tool 3: `get_historical_trend(group_by: Literal["hour","shift","lot","day"], filters: dict)`
- **Input:** `group_by` và filter tùy chọn (`shift_id`, `lot_id`, `station_id`, khoảng ngày).
- **Output:** aggregation `defects per lot/shift/day`, `scratch_rate`, `dent_rate`, `pass_fail_rate` — dùng cho `QC_SUPERVISOR` dashboard (`PRD.md` §6.3), tách biệt khỏi Tool 2 (Sliding Window realtime).

---

## 6. FastAPI REST & Realtime Streaming Endpoints

### 6.1. `POST /api/v1/inspect`
Khởi chạy quy trình kiểm định ảnh trạm FNS và kiểm tra bất thường hệ thống. Yêu cầu request đã xác thực bằng Supabase access token hợp lệ (xem §6.7); role `QC_OPERATOR` hoặc `QC_SUPERVISOR`.

**Request:** `multipart/form-data`
- `file`: Ảnh chụp trạm FNS (`image/jpeg` hoặc `image/png`)
- `vehicle_id`: `"CAR-20260816-001"`
- `station_id`: `"QC-01"`
- `lot_id` *(tùy chọn)*: `"LOT-20260816-A"`
- `shift_id` *(tùy chọn)*: `"SHIFT-A"`

**Response:** `200 OK`
```json
{
  "success": true,
  "inspection_id": "INSP-20260816-001",
  "vehicle_id": "CAR-20260816-001",
  "result": {
    "status": "FAIL",
    "recommended_plan": "PLAN_B_HOLD",
    "allow_test_drive": false,
    "rework_destination": "Rework Shop (Body & Paint)",
    "overall_rank": "A",
    "reasoning_summary": "Phát hiện vết móp tại vùng Class A nhưng chưa có phép đo độ sâu được xác nhận. Giữ xe chờ QC đo và đối chiếu tiêu chí demo.",
    "defects": [
      {
        "defect_id": "DEF-001",
        "type": "dent",
        "zone_name": "door_front_left_class_a",
        "gdt_group": "Group 1",
        "tolerance_limit_mm": 0.7,
        "tolerance_status": "DEMO_BASELINE_ONLY",
        "measured_depth_mm": null,
        "physical_measurement_status": "REQUIRES_CALIBRATION_OR_QC_MEASUREMENT",
        "geometry": {
          "area_px": 5200,
          "orientation_deg": 4.7,
          "centroid": [575, 255]
        },
        "severity_rank": "A",
        "action": "Hold for Rework"
      }
    ],
    "systemic_anomaly": {
      "is_alert": true,
      "consecutive_count": 3,
      "message": "CẢNH BÁO CHUỖI BẤT THƯỜNG: 3 xe liên tiếp bị móp tại vùng Cánh cửa trước trái.",
      "predicted_root_cause": "Khuôn dập Xưởng Dập dính bavia kim loại.",
      "root_cause_evidence": "COORDINATE_CLUSTER_CONFIRMED",
      "root_cause_evidence_detail": {
        "coordinate_cluster": true,
        "single_camera": true,
        "severity_at_least_warning": true,
        "occurrence_count": 3
      },
      "line_prevention_command": "Điều hướng xe vào Làn Đệm Offline — Giữ Line chính tiếp tục chạy."
    }
  },
  "created_at": "2026-08-16T12:00:02Z"
}
```

---

### 6.2. `GET /api/v1/station/stream-alerts` (Server-Sent Events / SSE)
Stream trực tiếp các cảnh báo bất thường chuỗi (Sliding Window realtime) và trạng thái line tới Dashboard Trưởng ca và Màn hình trạm FNS.

**SSE Event:**
```json
event: systemic_anomaly_alert
data: {
  "timestamp": "2026-08-16T12:00:02Z",
  "station_id": "QC-01",
  "alert_level": "HIGH",
  "defect_type": "dent",
  "zone": "door_front_left_class_a",
  "consecutive_cars": ["VN8921-2026-01", "VN8921-2026-02", "VN8921-2026-03"],
  "predicted_root_cause": "Vết móp lặp lại tại cùng một tọa độ, cùng camera, trên đủ số xe liên tiếp để loại trừ trùng hợp ngẫu nhiên — giả thuyết: khuôn dập (stamping die) dính bavia/mạt kim loại hoặc tay gắp robot bị kẹt dị vật đúng vị trí đó. Cần QC xác minh trực tiếp thiết bị trước khi kết luận.",
  "root_cause_evidence": "COORDINATE_CLUSTER_CONFIRMED",
  "root_cause_evidence_detail": {
    "coordinate_cluster": true,
    "single_camera": true,
    "severity_at_least_warning": true,
    "occurrence_count": 3
  },
  "instruction": "Kiểm tra khuôn dập số 2 tại Xưởng Dập. Kích hoạt làn đệm kiểm tra số 2."
}
```

`root_cause_evidence` (`COORDINATE_CLUSTER_CONFIRMED` | `ZONE_ONLY_UNCONFIRMED`) và
`root_cause_evidence_detail` — xem giải thích đầy đủ ở §6.4, cùng ý nghĩa cho cả SSE và
`GET /api/quality-alerts`.

### 6.3. Quy tắc tương thích
- `POST /api/v1/inspect` là facade contract; bên trong chạy cùng LangGraph workflow với `/inspections/from-image`. `result.status` trong response §6.1 là chính giá trị `QCState.final_status` (`PASS | FAIL` — mục 3), không phải một enum riêng cho endpoint này.
- `recommended_plan` phục vụ tương thích client cũ, ánh xạ một-một từ `final_status`: `PLAN_A_BUFFING` ⇐ `PASS`; `PLAN_B_HOLD` ⇐ `FAIL`. `concrete_action` được ánh xạ trực tiếp từ `QCState.recommendation_code`, là mã hành động vận hành chuẩn (dùng để phân biệt lý do FAIL chi tiết hơn, khi cần).
- `estimated_depth_mm` phải là `null` nếu không có depth sensor hoặc phép đo QC. `surface_area_mm2` có thể là ước lượng khi có profile camera cố định, nhưng phải kèm `physical_measurement_status=PILOT_FIXED_CAMERA_ESTIMATE_NOT_QC_APPROVED` và `calibration_profile_id`.
- `geometry` là trường mới, additive; client cũ không đọc trường này vẫn tương thích ngược vì nó optional.
- SSE dùng sliding window 10 xe từ repository. Baseline dùng Supabase/PostgreSQL; Redis có thể thay adapter mà không đổi contract.
- Contract baseline không nhận hoặc trả `vin_code`, `panel`, `material`. Dùng
  `vehicle_id` để định danh vận hành và `zone_name` cho vùng quan sát tương đối.

### 6.4. `GET /api/quality-alerts`

Trả summary dùng cho trang Cảnh báo lặp lỗi (Sliding Window realtime). UI sử dụng các trường chính:

- `alerts[].related_defect_codes`: các mã lỗi liên quan;
- `alerts[].occurrences[].image_url`: ảnh bằng chứng từng inspection (resolved từ object storage key);
- `occurrence_count`, `affected_vehicle_count`, `camera_id`, `last_seen`;
- `recommendation_vi/en`, `predicted_root_cause`, `root_cause_evidence`,
  `root_cause_evidence_detail`, `upstream_target_shop`;
- `upstream_checks_vi/en`: checklist hành động, UI chỉ hiển thị ba bước đầu.

`alerts[].root_cause_evidence` (`COORDINATE_CLUSTER_CONFIRMED` | `ZONE_ONLY_UNCONFIRMED`) cho
biết `predicted_root_cause` có phải là giả thuyết thực sự dựa trên bằng chứng hay không — PRD.md
§6.1 yêu cầu root cause luôn là "giả thuyết cần QC xác minh, không phải kết luận chắc chắn".
`COORDINATE_CLUSTER_CONFIRMED` chỉ được trả về khi **cả ba** tín hiệu trong
`alerts[].root_cause_evidence_detail` đều `true`:

- `coordinate_cluster`: các occurrence cụm lại gần cùng một tọa độ khung hình (không chỉ cùng
  `zone_name` — 5 vùng thân xe thô, có thể rải rác trong cùng một vùng);
- `single_camera`: mọi occurrence đến từ cùng một camera (xuyên camera là bằng chứng yếu hơn);
- `severity_at_least_warning`: nhóm đạt tối thiểu WARNING, không dừng ở WATCH (có thể chỉ 2 xe —
  mẫu quá nhỏ để nêu đích danh thiết bị).

Thiếu một trong ba, kết quả là `ZONE_ONLY_UNCONFIRMED` và `predicted_root_cause` chỉ nêu các khả
năng cần xác minh thêm, không khẳng định một cơ chế cụ thể. `root_cause_evidence_detail` còn có
`occurrence_count` (số occurrence trong nhóm) để tham khảo. UI phải hiển thị field này (không chỉ
text) để QC không hiểu nhầm một giả thuyết chưa xác nhận thành kết luận đã đúng.

Frontend loại `image_url` trùng và hiển thị tối đa bốn ảnh trên mỗi cảnh báo.
Nếu không có ảnh, UI phải hiện trạng thái rỗng rõ ràng thay vì placeholder giả.

### 6.5. `GET /api/trend` (Historical Trend)

Trả aggregation theo `group_by=hour|shift|lot|day` (Tool 3, mục 5), dùng cho
`QC_SUPERVISOR` dashboard. Không dùng chung endpoint với `GET
/api/v1/station/stream-alerts` (SSE realtime) để giữ tách biệt Sliding Window
vs Historical Trend (`PRD.md` §6.3).

### 6.6. Dữ liệu Hàng đợi QC và Lịch sử

`GET /agent/runs` là nguồn chung cho hai màn hình:

- run `INTERRUPTED` đi vào Hàng đợi QC, kèm `interrupt.reason` để giải thích vì
  sao cần kiểm duyệt (bao gồm các lý do HITL ở `PRD.md` §7.6: low
  confidence, unknown defect class, missing evidence, reasoning LLM
  unavailable/invalid);
- run `COMPLETED` đi vào Lịch sử, hiển thị `state.image_url`,
  `classified_defect_code`, `confidence`, `geometry`,
  `camera_id`, `recommendation` và `final_status`;
- nhấn bản ghi mở lại inspection state đầy đủ; `DELETE /agent/runs` chỉ xóa
  trace/state, không xóa file evidence đã upload trên object storage.

### 6.6b. HITL Resume (`POST /inspections/{thread_id}/resume`)

LangGraph có **hai cấp HITL** (`agent/graph/nodes.py`): `human_review` (QC Inspector) và, chỉ khi Inspector chọn chuyển cấp, `supervisor_review` (QC Supervisor). Cùng một request schema (`LangGraphResumeRequest`) dùng cho cả hai cấp:

```python
action: str        # human_review: "APPROVE" | "REJECT" | "OVERRIDE"
                    # supervisor_review: "UPHOLD_POLICY" | <id của một policy APPROVED>
reviewer: str
reason: str
defect_code: str | None       # sửa lại mã lỗi -- CHỈ dùng khi ca có ≤1 finding chưa phân loại
severity: str | None
disposition: Literal["PASS", "HOLD", "REPAIR"] | None  # ghi vào qc_decision_record khi có defect_code
recommendation: str | None     # ghi chú bối cảnh khi action = OVERRIDE, không quyết định final_status
detection_resolutions: list[DetectionResolution] | None  # bắt buộc khi ca có ≥2 finding chưa phân loại

# DetectionResolution:
#   detection_id: str   # camera_classifications[].detection_id đang chờ (classified_defect_code == null)
#   defect_code: str
#   severity: str | None
```

- **Ở `human_review` (Inspector):** `APPROVE` xác nhận lỗi AI gắn cờ là thật → `final_status = FAIL` (chuyển Rework). `REJECT` bác bỏ lỗi AI gắn cờ (không phải lỗi thật) → `final_status = PASS` ngay lập tức — **không có bước tái kiểm tra (reinspect) riêng nào khác**. `OVERRIDE` chuyển case sang cấp `supervisor_review` (`hitl_status = OVERRIDDEN`); `recommendation` bắt buộc nhưng chỉ là ghi chú bối cảnh hiển thị cho Supervisor, không tự trở thành quyết định.
- **Ở `supervisor_review` (chỉ role `QC_SUPERVISOR` mới gọi được, 403 nếu không đúng role):** Supervisor không thể tự đặt PASS/FAIL tùy ý — họ chỉ được chọn giữa `UPHOLD_POLICY` (giữ nguyên quyết định tự động của QC Rules, y hệt như case chưa từng bị `OVERRIDE`) hoặc `action = <policy_id>` của **một chính sách `checklist_status = APPROVED`** đang có trong catalog (`GET /api/policies`) — server xác thực lại `policy_id` đó còn tồn tại và còn APPROVED trước khi áp dụng (`QCNodes.supervisor_review`/`generate_recommendation`, `agent/graph/nodes.py`). Kết quả `action_code`/`final_status`/`required_evidence` khi đó lấy nguyên từ chính policy đã chọn (`PolicyCatalog.evaluate_named`) — không có `action_code` tự chế từ text tự do, và không hardcode `FAIL`. Dropdown chính sách hợp lệ ở FE lấy TOÀN BỘ policy `APPROVED` trong catalog (`PolicyCatalog.list_approved_policies()`), **không** lọc thêm theo `defect_type` của case.
- `disposition` chỉ là nhãn audit ghi vào `qc_decision_record` khi request có kèm `defect_code` (sửa mã lỗi) — không điều khiển `final_status`. Ba giá trị: `PASS`, `HOLD` (đang chờ xử lý tiếp, ví dụ khi vừa `OVERRIDE`), `REPAIR` (xác nhận chuyển sửa chữa). Không còn giá trị `REWORK`/`REINSPECT` cũ.
- **`detection_resolutions` (nhiều finding độc lập chưa phân loại):** một ca có thể có nhiều detection cùng cần HITL (mỗi camera/mỗi vùng lỗi được phân loại độc lập — xem 6.6a). Nếu số finding với `classified_defect_code == null` trong `camera_classifications` là:
  - **≤ 1**: dùng `defect_code` như cũ (tương thích ngược, không bắt buộc đổi client cũ).
  - **≥ 2**: **bắt buộc** gửi `detection_resolutions` — một phần tử cho MỖI `detection_id` đang chờ, không thiếu không thừa (422 nếu lệch). Gửi `defect_code` đơn trong trường hợp này cũng bị từ chối 422 (yêu cầu dùng `detection_resolutions`) — tránh tái diễn lỗi cũ là một mã bị áp nhầm cho mọi finding chưa phân loại. Trường `classified_defect_code`/`severity` ở cấp ca (top-level, dùng cho `qc_decision_record`) khi đó lấy theo finding "nặng nhất" (`detection_priority_key`, cùng quy ước worst-wins với `QCNodes.detect_defect`).

### 6.7. Authentication & RBAC (Supabase Auth)

Đăng nhập baseline dùng **Supabase Auth**; FastAPI backend không tự phát
hành hay lưu mật khẩu — nó chỉ **xác thực (verify)** access token do
Supabase Auth cấp và **tra cứu role** trong bảng `profiles`
(`ENVIRONMENT.md`). Điều này tránh xây hai cơ chế auth song song
(`POLICY_GOVERNANCE.md`).

- **Frontend đăng nhập trực tiếp với Supabase Auth** bằng Supabase client SDK
  (`NEXT_PUBLIC_SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_ANON_KEY`) — không gọi
  qua backend cho bước đăng nhập. Sau khi đăng nhập, frontend nhận Supabase
  access token và gắn vào header `Authorization: Bearer <supabase_access_token>`
  cho mọi request tới FastAPI.
- **`GET /api/auth/me`** (backend, canonical): backend verify access token
  bằng `SUPABASE_JWT_SECRET`, lấy `sub` (user id), tra `profiles.role`, trả
  `{ "user_id": ..., "email": ..., "role": "QC_OPERATOR" | "QC_SUPERVISOR" }`
  làm current-user context cho frontend. Đây là endpoint duy nhất backend
  cần cung cấp cho luồng auth — không có `POST /api/auth/login` phía backend
  vì việc đăng nhập do Supabase Auth xử lý.
- Mọi endpoint ghi dữ liệu (`/api/v1/inspect`, `/inspections/from-image`,
  HITL resume, QC Rules management) yêu cầu access token Supabase hợp lệ;
  endpoint quản lý QC Rules và historical trend yêu cầu role
  `QC_SUPERVISOR` sau khi tra `profiles.role` (xem `POLICY_GOVERNANCE.md`).
- Tài khoản mới mặc định nhận role `DEFAULT_QC_ROLE` (`QC_OPERATOR`) khi
  `profiles` được tạo lần đầu; đổi role sang `QC_SUPERVISOR` là thao tác
  quản trị thủ công (Supabase dashboard hoặc script nội bộ), không phải một
  API public trong baseline MVP.
