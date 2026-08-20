# API Contract & Data Schemas
# Visual QC Agent (Team 235) — Automotive FNS Station

Tài liệu quy chuẩn giao tiếp (Data Contracts) giữa:
1. **YOLO Segmentation (Vision Engine: Scratch & Dent Detection)**
2. **Geometry Processor (Deterministic Geometry Extraction)**
3. **Multimodal LLM (Visual Verification, Description, Explainability)**
4. **LangGraph Agent (Industrial Domain Reasoning & Anomaly Engine)**
5. **Backend API (FastAPI Gateway) + S3/MinIO Object Storage + PostgreSQL/Supabase**
6. **Workstation UI (Next.js Touch Dashboard)**

Xem `PRD.md` §2 cho sơ đồ kiến trúc tổng thể và `POLICY_GOVERNANCE.md` cho ranh
giới thẩm quyền của từng thành phần. Mỗi nhóm field dưới đây ghi rõ provenance
(`source = yolo | geometry_processor | multimodal_llm | camera_calibration |
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
  "station_id": "FNS_LINE_HA_01",
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

## 3. Multimodal LLM Output Schema (`VisualAssessment`)

Multimodal LLM nhận ảnh gốc, crop vùng lỗi, overlay/mask hoặc polygon, YOLO
class/confidence và zone/camera metadata — không chỉ text/JSON (`source =
multimodal_llm`). Output là **visual cross-check và semantic description**,
không phải physical measurement và không phải quyết định PASS/FAIL — xem
`POLICY_GOVERNANCE.md` (Multimodal LLM governance boundaries).

```json
{
  "defect_id": "DEF-001",
  "visual_verification": "SUPPORTED",
  "shape_pattern": "thin_linear",
  "continuity": "continuous",
  "distribution": "localized",
  "visibility": "clear",
  "possible_artifact": "none",
  "visual_uncertainty": "LOW",
  "description": "Vùng được đánh dấu có dạng tuyến tính mảnh, liên tục và có độ tương phản rõ với bề mặt sơn xung quanh."
}
```

`visual_verification` chỉ nhận `SUPPORTED | CONFLICT | UNCERTAIN`.
`visual_uncertainty` chỉ nhận `LOW | MEDIUM | HIGH`. Một `VisualAssessment`
với `visual_verification=CONFLICT` hoặc `visual_uncertainty=HIGH` phải kích
hoạt HITL (mục 4.1, `FR-15` trong `PRD.md`) và không được tự chuyển thành
PASS.

Sau khi LangGraph + QC Rules có quyết định, Multimodal LLM sinh thêm
`explanation` (text) gắn vào response cuối (mục 4.1) — trường này chỉ diễn
giải kết quả bất biến, không chứa giá trị PASS/FAIL/tolerance mới.

---

## 4. LangGraph Agent State Schema (`QCState`)

Được định nghĩa tại `agent/graph/state.py`. Schema quản lý cả luồng phán quyết xe đơn lẻ lẫn cơ chế phát hiện bất thường lặp lại (Systemic Anomaly). Node graph chuẩn hóa: `ingest → detect → extract_visual_geometry → multimodal_verify → classify → decide → decision_gate → (final_decide | HITL → human_review → resume → final_decide) → explain → complete → update_trend` (trục chính `detect → classify → decide → HITL`). `explain` luôn chạy sau final decision, không bao giờ trước HITL, vì kết luận có thể đổi sau khi QC xác nhận/override — xem `POLICY_GOVERNANCE.md`. Trạng thái triển khai runtime tại `AGENT_FLOW.md`.

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

class VisualAssessment(BaseModel):
    # source = multimodal_llm — visual cross-check, không phải ground truth
    visual_verification: Literal["SUPPORTED", "CONFLICT", "UNCERTAIN"]
    shape_pattern: Optional[str] = None
    continuity: Optional[str] = None
    distribution: Optional[str] = None
    visibility: Optional[str] = None
    possible_artifact: Optional[str] = None
    visual_uncertainty: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    description: Optional[str] = None

class DefectItem(BaseModel):
    defect_id: str
    type: Literal["dent", "scratch"]
    confidence: float  # source = yolo
    bbox: List[int]  # [xmin, ymin, xmax, ymax] — source = yolo
    mask_image_key: Optional[str] = None
    crop_image_key: Optional[str] = None
    geometry: Optional[GeometryFeatures] = None
    visual_assessment: Optional[VisualAssessment] = None
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
    enriched_defects: List[DefectItem]  # detections + geometry + visual_assessment + operational metadata
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
    final_status: str  # business decision chuẩn: PASS | HOLD_FOR_QC | HOLD_FOR_REWORK | HUMAN_OVERRIDE_APPLIED

    # 2. Cảnh báo Bất thường Chuỗi & Chống Dừng Line (Systemic Anomaly, realtime sliding window)
    anomaly_alert: Optional[SystemicAnomalyAlert]

    # 3. Human-In-The-Loop
    hitl_status: Literal["PENDING", "CONFIRMED", "OVERRIDDEN"]
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
- `detections`: output đã chuẩn hóa trực tiếp từ YOLO; `enriched_defects`: cùng finding sau khi Agent bổ sung `geometry` (Geometry Processor), `visual_assessment` (Multimodal LLM), zone và metadata vận hành.
- `severity` là mức độ tổng thể duy nhất; không tạo thêm alias `overall_severity_rank`.
- `recommendation_code`: mã hành động chuẩn duy nhất trong `QCState`; `recommendation` là mô tả dễ đọc.
- `recommended_plan` chỉ tồn tại ở response `/api/v1/inspect` để tương thích client cũ. `final_action` không còn thuộc contract.
- **`decision` vs `final_status` — không được dùng lẫn nhau:** `decision` là mã trạng thái nội bộ do node `assess_result`/`human_review` sinh ra để mô tả *vì sao* graph chọn nhánh này (ví dụ `DEFECT_CONFIRMED`, `UNKNOWN_CLASS_REVIEW_REQUIRED`, `MODEL_ERROR_REVIEW_REQUIRED`, `LLM_AGENT_UNAVAILABLE`, `REINSPECTION_REQUIRED`) — đây là lý do vận hành/chẩn đoán, không phải phán quyết QC cuối cùng. **`final_status` mới là business decision chuẩn** hiển thị cho QC và đối chiếu với đề bài (PASS/FAIL/cần người kiểm — mục 5.3 `PRD.md`), do QC Rules (`agent/services/policy.py` + `agent/policies/qc_policy_catalog.json`) quyết định; giá trị hiện có trong controlled catalog: `PASS` (release), `HOLD_FOR_QC` (evidence chưa đủ rõ, cần QC thẩm định thêm — tương đương REVIEW), `HOLD_FOR_REWORK` (lỗi xác nhận vượt tolerance, giữ xe chuyển rework — tương đương FAIL), `HUMAN_OVERRIDE_APPLIED` (QC override qua HITL). UI chỉ hiển thị `final_status`, không hiển thị `decision` thô cho QC (xem `UI_WORKFLOWS.md`).
- `hitl_status` chỉ có 3 giá trị thật (`PENDING`, `CONFIRMED`, `OVERRIDDEN`); không có trạng thái `NOT_REQUIRED` riêng — khi HITL không cần thiết, `hitl_status` được gán thẳng `CONFIRMED` (đã xác nhận tự động qua QC Rules, không cần người), không phải một literal khác.
- `original_image_key`/`overlay_image_key`/`mask_image_key`/`crop_image_key`: S3/MinIO object key, không phải binary; xem mục 5.

---

## 5. Object Storage (S3/MinIO) Layout

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

## 6. Tool Interfaces & Domain Engines

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
    "upstream_target_shop": "Stamping Shop / Framing Robot 04",
    "line_stoppage_risk": "HIGH",
    "action_plan": "1. Gửi cảnh báo khẩn đến Trưởng ca Xưởng Dập. 2. Đề xuất điều hướng các xe lỗi vào Vùng đệm Offline để tránh dừng Line FNS chính (Trưởng ca xác nhận và thực thi thao tác điều hướng)."
  }
  ```

### Tool 3: `get_historical_trend(group_by: Literal["hour","shift","lot","day"], filters: dict)`
- **Input:** `group_by` và filter tùy chọn (`shift_id`, `lot_id`, `station_id`, khoảng ngày).
- **Output:** aggregation `defects per lot/shift/day`, `scratch_rate`, `dent_rate`, `pass_fail_rate` — dùng cho `QC_SUPERVISOR` dashboard (`PRD.md` §6.3), tách biệt khỏi Tool 2 (Sliding Window realtime).

---

## 7. FastAPI REST & Realtime Streaming Endpoints

### 7.1. `POST /api/v1/inspect`
Khởi chạy quy trình kiểm định ảnh trạm FNS và kiểm tra bất thường hệ thống. Yêu cầu request đã xác thực bằng Supabase access token hợp lệ (xem §7.7); role `QC_OPERATOR` hoặc `QC_SUPERVISOR`.

**Request:** `multipart/form-data`
- `file`: Ảnh chụp trạm FNS (`image/jpeg` hoặc `image/png`)
- `vehicle_id`: `"CAR-20260816-001"`
- `station_id`: `"FNS_LINE_HA_01"`
- `lot_id` *(tùy chọn)*: `"LOT-20260816-A"`
- `shift_id` *(tùy chọn)*: `"SHIFT-A"`

**Response:** `200 OK`
```json
{
  "success": true,
  "inspection_id": "INSP-20260816-001",
  "vehicle_id": "CAR-20260816-001",
  "result": {
    "status": "HOLD_FOR_REWORK",
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
        "visual_assessment": {
          "visual_verification": "SUPPORTED",
          "shape_pattern": "thin_linear",
          "continuity": "continuous",
          "distribution": "localized",
          "visibility": "clear",
          "possible_artifact": "none",
          "visual_uncertainty": "LOW"
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
      "line_prevention_command": "Điều hướng xe vào Làn Đệm Offline — Giữ Line chính tiếp tục chạy."
    }
  },
  "created_at": "2026-08-16T12:00:02Z"
}
```

---

### 7.2. `GET /api/v1/station/stream-alerts` (Server-Sent Events / SSE)
Stream trực tiếp các cảnh báo bất thường chuỗi (Sliding Window realtime) và trạng thái line tới Dashboard Trưởng ca và Màn hình trạm FNS.

**SSE Event:**
```json
event: systemic_anomaly_alert
data: {
  "timestamp": "2026-08-16T12:00:02Z",
  "station_id": "FNS_LINE_HA_01",
  "alert_level": "HIGH",
  "defect_type": "dent",
  "zone": "door_front_left_class_a",
  "consecutive_cars": ["VN8921-2026-01", "VN8921-2026-02", "VN8921-2026-03"],
  "instruction": "Kiểm tra khuôn dập số 2 tại Xưởng Dập. Kích hoạt làn đệm kiểm tra số 2."
}
```

### 7.3. Quy tắc tương thích
- `POST /api/v1/inspect` là facade contract; bên trong chạy cùng LangGraph workflow với `/inspections/from-image`. `result.status` trong response §7.1 là chính giá trị `QCState.final_status` (`PASS | HOLD_FOR_QC | HOLD_FOR_REWORK | HUMAN_OVERRIDE_APPLIED` — mục 4), không phải một enum riêng cho endpoint này.
- `recommended_plan` phục vụ tương thích client cũ, ánh xạ nhiều-về-một từ `final_status`: `PLAN_A_BUFFING` ⇐ `PASS`; `PLAN_B_HOLD` ⇐ `HOLD_FOR_REWORK` hoặc `HOLD_FOR_QC` (client cũ không phân biệt hai loại HOLD; client mới phải đọc `final_status` để phân biệt). `concrete_action` được ánh xạ trực tiếp từ `QCState.recommendation_code`, là mã hành động vận hành chuẩn.
- `estimated_depth_mm` phải là `null` nếu không có depth sensor hoặc phép đo QC. `surface_area_mm2` có thể là ước lượng khi có profile camera cố định, nhưng phải kèm `physical_measurement_status=PILOT_FIXED_CAMERA_ESTIMATE_NOT_QC_APPROVED` và `calibration_profile_id`.
- `geometry` và `visual_assessment` là các trường mới, additive; client cũ không đọc các trường này vẫn tương thích ngược vì chúng optional.
- SSE dùng sliding window 10 xe từ repository. Baseline dùng Supabase/PostgreSQL; Redis có thể thay adapter mà không đổi contract.
- Contract baseline không nhận hoặc trả `vin_code`, `panel`, `material`. Dùng
  `vehicle_id` để định danh vận hành và `zone_name` cho vùng quan sát tương đối.

### 7.4. `GET /api/quality-alerts`

Trả summary dùng cho trang Cảnh báo lặp lỗi (Sliding Window realtime). UI sử dụng các trường chính:

- `alerts[].related_defect_codes`: các mã lỗi liên quan;
- `alerts[].occurrences[].image_url`: ảnh bằng chứng từng inspection (resolved từ object storage key);
- `occurrence_count`, `affected_vehicle_count`, `camera_id`, `last_seen`;
- `recommendation_vi/en`, `predicted_root_cause`, `upstream_target_shop`;
- `upstream_checks_vi/en`: checklist hành động, UI chỉ hiển thị ba bước đầu.

Frontend loại `image_url` trùng và hiển thị tối đa bốn ảnh trên mỗi cảnh báo.
Nếu không có ảnh, UI phải hiện trạng thái rỗng rõ ràng thay vì placeholder giả.

### 7.5. `GET /api/trend` (Historical Trend)

Trả aggregation theo `group_by=hour|shift|lot|day` (Tool 3, mục 6), dùng cho
`QC_SUPERVISOR` dashboard. Không dùng chung endpoint với `GET
/api/v1/station/stream-alerts` (SSE realtime) để giữ tách biệt Sliding Window
vs Historical Trend (`PRD.md` §6.3).

### 7.6. Dữ liệu Hàng đợi QC và Lịch sử

`GET /agent/runs` là nguồn chung cho hai màn hình:

- run `INTERRUPTED` đi vào Hàng đợi QC, kèm `interrupt.reason` để giải thích vì
  sao cần kiểm duyệt (bao gồm các lý do HITL ở `PRD.md` §7.6/FR-15: low
  confidence, YOLO/LLM conflict, uncertainty HIGH, missing evidence, LLM
  unavailable/invalid);
- run `COMPLETED` đi vào Lịch sử, hiển thị `state.image_url`,
  `classified_defect_code`, `confidence`, `geometry`, `visual_assessment`,
  `camera_id`, `recommendation` và `final_status`;
- nhấn bản ghi mở lại inspection state đầy đủ; `DELETE /agent/runs` chỉ xóa
  trace/state, không xóa file evidence đã upload trên object storage.

### 7.7. Authentication & RBAC (Supabase Auth)

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
