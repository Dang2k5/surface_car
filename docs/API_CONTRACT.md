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
  "vin_code": "VN8921-2026-SUV01",
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
      "estimated_depth_mm": 1.15,
      "surface_area_mm2": 38.2,
      "zone_name": "door_front_left_class_a"
    }
  ]
}
```

---

## 2. LangGraph Agent State Schema (`QCState`)

Được định nghĩa tại `src/agents/state.py`. Schema quản lý cả luồng phán quyết xe đơn lẻ lẫn cơ chế phát hiện bất thường lặp lại (Systemic Anomaly):

```python
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

class DefectItem(BaseModel):
    defect_id: str
    type: Literal["dent", "scratch"]
    confidence: float
    bbox: List[int]  # [xmin, ymin, xmax, ymax]
    estimated_depth_mm: Optional[float] = None
    surface_area_mm2: Optional[float] = None
    zone_name: str
    gdt_group: Optional[Literal["Group 1", "Group 2", "Group 3", "Group 4", "Group 5"]] = None
    gdt_tolerance_allowed_mm: Optional[float] = None
    material_type: Optional[Literal["Hot Stamped Steel", "Mild Steel", "Galvanized Steel", "Aluminum"]] = None
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
    vin_code: str
    vehicle_model: str
    image_url: str
    raw_defects: List[Dict[str, Any]]
    enriched_defects: List[DefectItem]
    
    # 1. Phán quyết Xe Đơn lẻ (Individual Vehicle Decision)
    overall_severity_rank: Literal["P", "S", "A", "B", "C", "D", "NONE"]
    recommended_plan: Literal["PLAN_A_BUFFING", "PLAN_B_HOLD", "CRITICAL_HOLD", "PASS"]
    allow_test_drive: bool
    buffing_duration_minutes: Optional[int]
    rework_destination: Optional[str]
    reasoning_summary: str
    technical_explanations: List[str]
    
    # 2. Cảnh báo Bất thường Chuỗi & Chống Dừng Line (Systemic Anomaly)
    anomaly_alert: Optional[SystemicAnomalyAlert]
    
    # 3. Human-In-The-Loop
    hitl_status: Literal["PENDING", "CONFIRMED", "OVERRIDDEN"]
    inspector_override_reason: Optional[str]
    final_action: Optional[str]
```

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

### Tool 2: `lookup_material_properties(zone_name: str, vehicle_model: str)`
- **Input:** `zone_name`, `vehicle_model`
- **Output:**
  ```json
  {
    "zone_name": "door_front_left_class_a",
    "material": "Hot Stamped Steel",
    "rework_guideline": "CẤM GÕ NẮN NGUỘI TẠI TRẠM (Cold-working prohibited). Yêu cầu chuyển Rework xưởng thân vỏ chuyên dụng."
  }
  ```

### Tool 3: `analyze_defect_trend_anomaly(current_defects: list, window_size: int = 10)`
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
- `vin_code`: `"VN8921-2026-SUV01"`
- `station_id`: `"FNS_LINE_HA_01"`

**Response:** `200 OK`
```json
{
  "success": true,
  "inspection_id": "INSP-20260816-001",
  "vin_code": "VN8921-2026-SUV01",
  "result": {
    "status": "FAIL",
    "recommended_plan": "PLAN_B_HOLD",
    "allow_test_drive": false,
    "rework_destination": "Rework Shop (Body & Paint)",
    "overall_rank": "RANK A",
    "reasoning_summary": "Phát hiện vết móp 1.15mm vượt dung sai GD&T Group 1 (0.7mm) trên vật liệu Thép dập nóng. CẤM CHẠY THỬ để tránh bám bụi đất.",
    "defects": [
      {
        "defect_id": "DEF-001",
        "type": "dent",
        "zone_name": "door_front_left_class_a",
        "gdt_group": "Group 1",
        "tolerance_limit_mm": 0.7,
        "measured_depth_mm": 1.15,
        "material": "Hot Stamped Steel",
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
