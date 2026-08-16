# Visual QC Agent — Team 235
> **Hệ thống AI Agent Kiểm định Ngoại quan Thông minh & Cảnh báo Bất thường Chống Dừng Dây Chuyền tại Trạm FNS (Finish Line) — Line HA**

---

## 1. Project Brief (Tóm tắt Dự án)

### 1.1. Vấn đề & Nỗi đau Thực tế (Painpoints)
- **Tập trung vào 2 khuyết tật cốt lõi:** Tại trạm **FNS (Finish Line)**, hai loại lỗi ngoại quan xuất hiện nhiều nhất và gây tổn thất kinh tế lớn nhất là **Vết Xước (Scratch)** và **Vết Lõm / Móp (Dent)**.
- **Hạn chế của CV truyền thống:** Các giải pháp Computer Vision thông thường chỉ phát hiện bounding box, kiểm định viên QC vẫn mất **3 – 5 phút** lật tài liệu để đắn đo: *Lỗi này thuộc Rank nào (PSLAWBCD)? Vùng này là thép thường hay thép dập nóng (Hot Stamped Steel)? Dung sai GD&T cho phép bao nhiêu (Group 1–5: $0.7\text{mm} - 1.5\text{mm}$)? Nên cho xe chạy thử hay giữ lại?*
- **Rủi ro bẩn vết lỗi khi chạy thử:** Nếu xe bị móp sâu hoặc xước sơn mà vẫn lọt ra sân chạy thử, bụi đất và nước bắn vào vết hở làm hỏng lớp sơn lót, khiến việc sửa chữa (Rework) sau đó tốn chi phí gấp 5–10 lần.
- **Nỗi sợ lớn nhất của nhà máy: DỪNG LINE (Line Stoppage):** Khi một lỗi móp/xước lặp lại liên tiếp trên nhiều xe (do khuôn dập dính bavia hoặc tay gắp robot kẹp lệch), việc phát hiện muộn gây dồn ứ xe tại trạm FNS và buộc nhà máy phải **DỪNG DÂY CHUYỀN KHẨN CẤP** — gây tổn thất hàng chục nghìn USD mỗi giờ.

### 1.2. Giải pháp & Giá trị Đột phá của AI Agent
1. **Thị giác Máy tính Tập trung (Focused High-Precision CV):** Nhận dạng siêu chính xác 2 lớp lỗi `scratch` và `dent`, đo đạc ước tính độ sâu móp (`estimated_depth_mm`) và vị trí vùng thân vỏ (`zone_name`), loại bỏ báo động giả.
2. **Hạt nhân Lập luận Công nghiệp (Industrial Domain Engine):** Tự động đối chiếu tọa độ lỗi với bản đồ **GD&T (Group 1–5, Dung sai $0.7\text{mm} - 1.5\text{mm}$)**, loại vật liệu (**Thép thường vs Thép dập nóng**) và thang xếp rank **PSLAWBCD**.
3. **Phán quyết Điều hướng Tức thì (Actionable Routing < 2s):**
   - 🟢 **Phương án A (Buffing & Test Drive):** Lỗi nhẹ Rank C/D (xước bóng, móp nông vùng Group 2–4) $\rightarrow$ Đánh bóng nhanh 3 phút tại trạm $\rightarrow$ **XUẤT XANH CHO CHẠY THỬ**.
   - 🔴 **Phương án B (HOLD & Rework Shop):** Lỗi nặng Rank A/B, móp $>0.7\text{mm}$ (Group 1), hoặc chi tiết thép dập nóng $\rightarrow$ **GẮN NHÃN HOLD $\rightarrow$ CẤM CHẠY THỬ (Tránh bám bụi) $\rightarrow$ Chuyển thẳng xưởng Rework**.
4. **Phát hiện Bất thường Chuỗi & Chống Dừng Dây Chuyền (Systemic Anomaly & Line Stoppage Prevention):**
   - Giám sát Sliding Window $N = 10$ xe gần nhất.
   - Khi phát hiện $\ge 3$ xe liên tiếp cùng bị móp/xước tại 1 vị trí $\rightarrow$ Lập tức phát **Cảnh báo Sớm Nguyên nhân Gốc rễ** tới Xưởng Dập/Hàn thượng nguồn và kích hoạt **Điều phối Làn Đệm (Offline Buffer Routing)** giúp dây chuyền chính **TIẾP TỤC CHẠY BÌNH THƯỜNG, KHÔNG BỊ DỪNG LINE**.

### 1.3. Đối tượng sử dụng
- **Kiểm định viên QC (QC Inspector):** Thao tác trực tiếp tại trạm FNS trên màn hình cảm ứng.
- **Giám sát viên chất lượng & Trưởng ca (QC / Line Supervisor):** Theo dõi dashboard cảnh báo dừng line và phân tích xu hướng lỗi.
- **Kỹ thuật viên Rework (Rework Technician):** Tiếp nhận xe Plan B kèm hồ sơ lỗi và hướng dẫn xử lý kỹ thuật.

---

## 2. PRD (Tài liệu Yêu cầu Sản phẩm)

### Mục tiêu (Product Goals)
- **Chu kỳ ra quyết định:** Tự động hóa đánh giá và phân luồng từ 3–5 phút xuống **< 2 giây/loại lỗi**.
- **Độ chính xác nhận diện Xước & Móp (CV mAP@0.5):** Đạt $\ge 90\%$.
- **Độ chính xác phân luồng Plan A / Plan B:** Đạt $\ge 96\%$.
- **Khả năng chống dừng line:** Phát hiện sớm các lỗi chuỗi bất thường trong vòng $\le 3$ xe lỗi để kích hoạt điều phối đệm.
- **Tích hợp Human-In-The-Loop (HITL):** Cho phép công nhân trạm xác nhận hoặc ghi đè (Override) phán quyết kèm lý do.

---

### Ma trận Ra quyết định & Hành động (Decision & Action Matrix)

| Loại Khuyết tật | Vị trí / Vùng GD&T | Vật liệu Thân vỏ | Severity Rank | Phán quyết Agent | Hành động Điều hướng Thực thi |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Xước dăm / Xước nông (Scratch)** | Cánh cửa / Cột (Group 2–4) | Thép mạ kẽm thường | **Rank C / D** | **PLAN A** | Đánh bóng (Buffing) 3 phút tại trạm $\rightarrow$ **XUẤT XANH CHẠY THỬ** |
| **Vết móp nông ($\le 0.7\text{mm}$)** | Mui xe / Tai xe (Group 2–3) | Thép thường | **Rank C** | **PLAN A** | Xử lý nhanh tại trạm $\rightarrow$ **CHO PHÉP CHẠY THỬ** |
| **Vết móp sâu ($> 0.7\text{mm}$)** | Cánh cửa Class A (Group 1) | Thép thường | **Rank A / B** | **PLAN B** | **GẮN NHÃN HOLD $\rightarrow$ CẤM CHẠY THỬ** (Tránh bụi bẩn) $\rightarrow$ Chuyển Rework |
| **Vết móp biến dạng** | Khung cửa Class A (Group 1) | **Thép dập nóng (Hot Stamped)** | **Rank A** | **PLAN B** | **GẮN NHÃN HOLD $\rightarrow$ CẤM CHẠY THỬ** (Không nắn nguội), Rework chuyên dụng |
| **Xước sâu chạm kim loại** | Nắp capo Class A (Group 1) | Mọi vật liệu | **Rank A / B** | **PLAN B** | **GẮN NHÃN HOLD $\rightarrow$ CẤM CHẠY THỬ** $\rightarrow$ Chuyển xưởng Sơn |

---

### Quy trình Kiểm tra & Tính năng Hệ thống

```mermaid
graph TD
    Input[Camera Trạm FNS] --> CV[CV Engine: Bắt chính xác Xước & Lõm]
    CV --> Agent[LangGraph Reasoning Engine]
    
    subgraph SingleRouting["1. Phán quyết Xe Đơn lẻ (<2s)"]
        Agent --> GDT[Tra cứu GD&T Group 1-5]
        GDT --> Mat[Tra cứu Vật liệu Thép thường vs Dập nóng]
        Mat --> Rank[Xếp Rank PSLAWBCD]
        Rank --> PlanChoice{Phân luồng}
        PlanChoice -->|Lỗi nhẹ| PlanA[PLAN A: Buffing 3m -> Cho Chạy Thử]
        PlanChoice -->|Lỗi nặng| PlanB[PLAN B: HOLD -> Cấm Chạy Thử -> Rework]
    end
    
    subgraph AnomalyDetection["2. Phát hiện Bất thường Chuỗi & Chống Dừng Line"]
        Agent --> SlidingBuffer[Redis Sliding Buffer: 10 xe gần nhất]
        SlidingBuffer --> CheckSpike{>= 3 xe liên tiếp<br/>cùng dính lỗi 1 vị trí?}
        CheckSpike -->|CÓ| TriggerAlert[CẢNH BÁO SỚM THƯỢNG NGUỒN<br/>(Khuôn dập / Robot kẹp)]
        TriggerAlert --> BufferRouting[Tự động Điều phối Xe Lỗi vào Làn Đệm Offline<br/>-> DÂY CHUYỀN CHÍNH TIẾP TỤC CHẠY]
    end
    
    PlanA & PlanB & BufferRouting --> HITL[QC Inspector Xác nhận / Override]
    HITL --> Report[Tự động Lưu Database & Xuất Báo cáo Nghiệm thu]
```

---

## 3. UI Flow & Wireframe

### Layout Giao diện Trạm QC (QC Workstation Interface Wireframe)

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⊗ VISUAL QC AGENT   [Station: FNS Line - HA]             Welcome, CÔNG NHÂN TRẠM QC [Logout]     │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 🚨 [SYSTEMIC ANOMALY ALERT]: 3 xe liên tiếp bị MÓP tại Cánh cửa trước trái (Group 1)!           │
│    -> Dự đoán: Khuôn dập Xưởng Dập dính bavia. Lệnh: Điều hướng Lô xe vào Làn đệm Offline.     │
├──────────────────────────────────────────────────────┬───────────────────────────┬───────────────┤
│ LIVE CAMERA & CV DETECTION (FNS LINE)                │ AGENT DECISION ENGINE     │ QC ACTION     │
│ ┌──────────────────────────────────────────────────┐ │ ┌───────────────────────┐ │ ┌───────────┐ │
│ │ VIN: VN8921-2026   | Model: SUV EV               │ │ │ RECOMMENDED ACTION:   │ │ │ CONFIRM   │ │
│ │ 🎯 DEFECT DETECTED: DENT ON DOOR FRONT-LH        │ │ │ 🔴 PLAN B (HOLD)      │ │ │ PLAN A    │ │
│ │ - Surface Zone: Class A (GD&T Group 1)           │ │ │                       │ │ │ (Buffing) │ │
│ │ - Tolerance Allowed: 0.7mm | Measured: 1.15mm    │ │ │ 🚫 DO NOT TEST DRIVE  │ │ ├───────────┤ │
│ │ - Material: Hot Stamped Steel                    │ │ │                       │ │ │ CONFIRM   │ │
│ │ - Severity Rank: RANK A (Structural Dent)        │ │ │ Route: Send to        │ │ │ PLAN B    │ │
│ └──────────────────────────────────────────────────┘ │ │ Rework Shop (Hot-Form)  │ │ │ (Hold)    │ │
│ Defect Type: DENT (Confidence: 95%)                  │ └───────────────────────┘ │ ├───────────┤ │
│ Status: FAIL (Exceeds GD&T Group 1 Tolerance)        │ REASONING LOGIC:          │ │ OVERRIDE  │ │
│ Consecutive Spike: CAR 3/3 (Anomaly Triggered)       │ - GD&T Group 1 Exceeded   │ │ DECISION  │ │
│                                                      │ - Hot Stamped Material    │ ├───────────┤ │
│                                                      │   cannot be cold-worked.  │ │ ASK AGENT │ │
│                                                      │ - Prevent road test dust. │ └───────────┘ │
├──────────────────────────────────────────────────────┴───────────────────────────┴───────────────┤
│ REAL-TIME VEHICLE ROUTING LOG (FNS LINE)                                                         │
│ Vehicle ID │ Defect Type │ GD&T Zone │ Severity Rank │ Recommended Action │ Status              │
│ CAR-9011   │ Scratch     │ Group 3   │ Rank C        │ Plan A (Buff 3m)   │ 🟢 Released to Test │
│ CAR-9012   │ Dent        │ Group 1   │ Rank A        │ Plan B (Hold/Form) │ 🔴 HELD (Buffer Ln) │
│ CAR-9013   │ Dent        │ Group 1   │ Rank A        │ Plan B (Hold/Form) │ 🔴 HELD (Buffer Ln) │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Phân công Thành viên & Tech Stack

### 4.1. Đội ngũ Phát triển (Team 235)
| Họ và tên | Vai trò | Trách nhiệm chính |
| :--- | :--- | :--- |
| **Phạm Bá Huy** | **PM (Project Manager & Deploy)** | Điều phối dự án, PRD, quản trị tiến độ, chuẩn bị Demo Day & Pitch Deck. Xây dựng báo cáo và triển khai sản phẩm. |
| **Đào Hải Đăng** | **PO (Product Owner & Computer Vision)** | Thiết kế luồng User Journey, Wireframe trạm QC, chuẩn hóa quy chuẩn công nghiệp. Xây dựng và tối ưu mô hình CV cho sản phẩm. |
| **Lê Quốc An** | **DEV (Backend, Frontend & Agent)** | Phát triển FastAPI backend, xây dựng LangGraph State Machine, tích hợp Phoenix. |
| **Hoàng Văn Thành** | **DEV (Benchmark & Test Engineer)** | Nghiên cứu tạo bộ Benchmark, đánh giá, thử nghiệm sản phẩm. |

### 4.2. Tech Stack
- **Frontend:** Next.js 14, React, Tailwind CSS, Canvas / SVG Overlay, Server-Sent Events (SSE).
- **Backend & APIs:** FastAPI (Python 3.11), REST API, Uvicorn, Pydantic v2.
- **Vision Engine:** PyTorch, YOLOv8, ONNX Runtime (Tối ưu hóa chuyên sâu Xước & Lõm).
- **Agent Orchestration:** LangGraph (State Graph, GD&T & Material Engine, Sliding Buffer Anomaly Monitor, HITL).
- **Database & Storage:** PostgreSQL (Metadata, CAD Specs), Redis (Realtime Sliding Buffer), MinIO / S3 (Image Archive).
- **Observability & Logging:** Arize Phoenix (LLM Tracing & Token Tracking).

---

## 5. AI Log Setup
- [x] Đã tạo API Key trên Phoenix
- [x] Đã tích hợp Hook vào Repo (`scripts/setup_hooks.ps1` & `scripts/setup_hooks.sh`)
- [x] Đã test log thành công
