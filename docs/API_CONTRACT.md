# API Contract & Data Schemas
# Visual QC Agent (Team 235) — Automotive FNS Station

Tài liệu quy chuẩn giao tiếp (Data Contracts) giữa:
1. **Vision Engine (Focused Computer Vision: Scratch & Dent Detection)**
2. **LangGraph State Machine (Industrial Domain Reasoning & Anomaly Engine)**
3. **Backend API (FastAPI Gateway)**
4. **Workstation UI (Next.js Touch Dashboard)**

---

## 1. Vision Engine Output Schema (`VisionDetectionResult`)

Mô hình Computer Vision tập trung nhận diện chuyên sâu 2 loại khuyết tật bề mặt: `scratch` (vết xước) và `dent` (vết lõm/móp).

```json
{
  "inspection_id": "INSP-20260816-001",
  "vehicle_id": "CAR-20260816-001",
  "timestamp": "2026-08-16T12:00:00Z",
  "camera_id": "CAM_FNS_DOOR_LH",
  "vehicle_model": "SUV_EV",
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
      "estimated_depth_mm": null,
      "surface_area_mm2": null,
      "physical_measurement_status": "REQUIRES_CALIBRATION_OR_QC_MEASUREMENT",
      "zone_name": "door_front_left_class_a"
    }
  ]
}
```

---

## 2. LangGraph Agent State Schema (`QCState`)

Được định nghĩa tại `agent/graph/state.py`. Schema quản lý cả luồng phán quyết xe đơn lẻ lẫn cơ chế phát hiện bất thường lặp lại (Systemic Anomaly):

```python
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

class DefectItem(BaseModel):
    defect_id: str
    type: Literal["dent", "scratch"]
    confidence: float
    bbox: List[int]  # [xmin, ymin, xmax, ymax]
    # Chỉ có giá trị khi camera đã calibration/depth-enabled hoặc QC đo xác nhận.
    estimated_depth_mm: Optional[float] = None
    surface_area_mm2: Optional[float] = None
    physical_measurement_status: str = "REQUIRES_CALIBRATION_OR_QC_MEASUREMENT"
    zone_name: str
    gdt_group: Optional[Literal["Group 1", "Group 2", "Group 3", "Group 4", "Group 5"]] = None
    gdt_tolerance_allowed_mm: Optional[float] = None
    severity_rank: Optional[Literal["P", "S", "A", "B", "C", "D"]] = None
    is_exceeding_tolerance: Optional[bool] = None

class SystemicAnomalyAlert(BaseModel):
    is_anomaly_detected: bool = False
    consecutive_defect_count: int = 0
    repetitive_zone: Optional[str] = None
    repetitive_defect_type: Optional[Literal["dent", "scratch"]] = None
    predicted_root_cause: Optional[str] = None  # Ví dụ: "Khuôn dập Die-02 dính bavia"
    upstream_target_shop: Optional[str] = None  # Ví dụ: "Stamping Shop Line 1"
    line_stoppage_risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"
    actionable_routing_command: Optional[str] = None # "Reroute batch to Offline Buffer Area"

class QCState(TypedDict):
    inspection_id: str
    thread_id: str
    vehicle_id: str
    vehicle_model: str
    image_url: str
    camera_id: str
    zone_name: str
    detections: List[Dict[str, Any]]
    enriched_defects: List[DefectItem]
    suggested_defect_codes: List[Dict[str, Any]]
    classified_defect_code: Optional[str]
    defect_family: Optional[str]
    defect_code_classification: Dict[str, Any]
    similar_defect_warning: bool
    agent_analysis: Dict[str, Any]
    
    # 1. Phán quyết Xe Đơn lẻ (Individual Vehicle Decision)
    severity: Literal["P", "S", "A", "B", "C", "D", "NONE", "UNASSESSED"]
    recommendation_code: str
    recommendation: str
    allow_test_drive: bool
    decision: str
    reason: str
    final_status: str
    
    # 2. Cảnh báo Bất thường Chuỗi & Chống Dừng Line (Systemic Anomaly)
    anomaly_alert: Optional[SystemicAnomalyAlert]
    
    # 3. Human-In-The-Loop
    hitl_status: Literal["PENDING", "CONFIRMED", "OVERRIDDEN"]
    human_required: bool
    human_decision: Optional[Dict[str, Any]]
```

### Quy ước tên trường

- `vehicle_id`: mã kỹ thuật bắt buộc để theo dõi một xe/phiên trong hệ thống.
- `zone_name`: vùng kiểm tra tương đối hoặc khu vực camera quan sát.
- `detections`: output đã chuẩn hóa trực tiếp từ detector; `enriched_defects`: cùng finding sau khi Agent bổ sung zone và metadata vận hành.
- `severity` là mức độ tổng thể duy nhất; không tạo thêm alias `overall_severity_rank`.
- `recommendation_code`: mã hành động chuẩn duy nhất trong `QCState`; `recommendation` là mô tả dễ đọc.
- `recommended_plan` chỉ tồn tại ở response `/api/v1/inspect` để tương thích client cũ. `final_action` không còn thuộc contract.

---

## 3. Tool Interfaces & Domain Engines

### Tool 1: `lookup_gdt_standard(zone_name: str, vehicle_model: str)`
- **Input:** `zone_name` (ví dụ: `"door_front_left_class_a"`), `vehicle_model` (`"SUV_EV"`)
- **Output:**
  ```json
  {
    "zone_name": "door_front_left_class_a",
    "gdt_group": "Group 1",
    "surface_class": "Class A",
    "max_tolerance_mm": 0.7,
    "inspection_rule": "Vết móp > 0.7mm hoặc xước sâu chạm kim loại cấm cho chạy thử."
  }
  ```

### Tool 2: `analyze_defect_trend_anomaly(current_defects: list, window_size: int = 10)`
- **Input:** Danh sách khuyết tật của xe hiện tại + Cửa sổ $N$ xe gần nhất trong ca.
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
    "action_plan": "1. Gửi cảnh báo khẩn đến Trưởng ca Xưởng Dập. 2. Tự động điều hướng các xe lỗi vào Vùng đệm Offline để tránh dừng Line FNS chính."
  }
  ```

---

## 4. FastAPI REST & Realtime Streaming Endpoints

### 4.1. `POST /api/v1/inspect`
Khởi chạy quy trình kiểm định ảnh trạm FNS và kiểm tra bất thường hệ thống.

**Request:** `multipart/form-data`
- `file`: Ảnh chụp trạm FNS (`image/jpeg` hoặc `image/png`)
- `vehicle_id`: `"CAR-20260816-001"`
- `station_id`: `"FNS_LINE_HA_01"`

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
    "overall_rank": "RANK A",
    "reasoning_summary": "Phát hiện vết móp tại vùng Class A nhưng chưa có phép đo độ sâu được xác nhận. Giữ xe chờ QC đo và đối chiếu tiêu chí OEM.",
    "defects": [
      {
        "defect_id": "DEF-001",
        "type": "dent",
        "zone_name": "door_front_left_class_a",
        "gdt_group": "Group 1",
        "tolerance_limit_mm": 0.7,
        "measured_depth_mm": null,
        "physical_measurement_status": "REQUIRES_CALIBRATION_OR_QC_MEASUREMENT",
        "severity_rank": "A",
        "action": "Plan B - Hold for Rework"
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

### 4.2. `GET /api/v1/station/stream-alerts` (Server-Sent Events / SSE)
Stream trực tiếp các cảnh báo bất thường chuỗi và trạng thái line tới Dashboard Trưởng ca và Màn hình trạm FNS.

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

### 4.3. Quy tắc tương thích
- `POST /api/v1/inspect` là facade contract; bên trong chạy cùng LangGraph workflow với `/inspections/from-image`.
- `recommended_plan` phục vụ tương thích client cũ. `concrete_action` được ánh xạ trực tiếp từ `QCState.recommendation_code`, là mã hành động vận hành chuẩn.
- `estimated_depth_mm` phải là `null` nếu không có depth sensor hoặc phép đo QC. `surface_area_mm2` có thể là ước lượng khi có profile camera cố định, nhưng phải kèm `physical_measurement_status=PILOT_FIXED_CAMERA_ESTIMATE_NOT_QC_APPROVED` và `calibration_profile_id`.
- SSE dùng sliding window 10 xe từ repository. Baseline dùng Supabase/PostgreSQL; Redis có thể thay adapter mà không đổi contract.
- Contract baseline không nhận hoặc trả `vin_code`, `panel`, `material`. Dùng
  `vehicle_id` để định danh vận hành và `zone_name` cho vùng quan sát tương đối.

### 4.4. `GET /api/quality-alerts`

Trả summary dùng cho trang Cảnh báo lặp lỗi. UI sử dụng các trường chính:

- `alerts[].related_defect_codes`: các mã lỗi liên quan;
- `alerts[].occurrences[].image_url`: ảnh bằng chứng từng inspection;
- `occurrence_count`, `affected_vehicle_count`, `camera_id`, `last_seen`;
- `recommendation_vi/en`, `predicted_root_cause`, `upstream_target_shop`;
- `upstream_checks_vi/en`: checklist hành động, UI chỉ hiển thị ba bước đầu.

Frontend loại `image_url` trùng và hiển thị tối đa bốn ảnh trên mỗi cảnh báo.
Nếu không có ảnh, UI phải hiện trạng thái rỗng rõ ràng thay vì placeholder giả.

### 4.5. Dữ liệu Hàng đợi QC và Lịch sử

`GET /agent/runs` là nguồn chung cho hai màn hình:

- run `INTERRUPTED` đi vào Hàng đợi QC, kèm `interrupt.reason` để giải thích vì
  sao cần kiểm duyệt;
- run `COMPLETED` đi vào Lịch sử, hiển thị `state.image_url`,
  `classified_defect_code`, `confidence`, `visual_measurements`, `camera_id`,
  `recommendation` và `final_status`;
- nhấn bản ghi mở lại inspection state đầy đủ; `DELETE /agent/runs` chỉ xóa
  trace/state, không xóa file evidence đã upload.
