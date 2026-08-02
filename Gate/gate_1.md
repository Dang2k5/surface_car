# Visual QC Agent - Team 235

## 1. Project Brief (Tóm tắt)
- **Vấn đề:** Kiểm tra thủ công chất lượng bề mặt thân vỏ xe hơi (phát hiện lỗi xước, móp, hỏng sơn) tốn nhiều thời gian, dễ gây mỏi mắt dẫn đến bỏ sót lỗi và quyết định PASS/FAIL mang tính chủ quan giữa các ca làm việc.
- **Giải pháp:** Xây dựng hệ thống Visual QC Agent tự động hóa quá trình kiểm tra 5 mặt thân vỏ xe bằng Computer Vision và Realtime Reasoning Engine, phân tích ảnh độ phân giải cao để phát hiện, khoanh vùng lỗi, đưa ra quyết định PASS/FAIL/REVIEW kèm lời giải thích theo thời gian thực.
- **Đối tượng:** Kiểm định viên QC (QC Inspector) và Giám sát viên QC (QC Supervisor) tại dây chuyền sản xuất lắp ráp ô tô - line HA.

## 2. PRD (Tài liệu yêu cầu sản phẩm)
### Mục tiêu (Goals)
- Xây dựng MVP kiểm định tự động 5 mặt xe (Trái, Phải, Trước, Sau, Nóc) với 3 loại lỗi chính (Xước, Sơn, Móp méo).
- Giảm thời gian chu kỳ kiểm tra xuống dưới 2.0s/xe cho cả 5 mặt với camera chuyên dụng và dưới 3 phút với camera công nghiệp.
- Tích hợp AI Reasoning Engine để giảm tỷ lệ bỏ sót lỗi (FAR ≈ 0%) thông qua cơ chế Human-In-The-Loop (HITL) đối với luồng REVIEW.
- Cung cấp Bảng điều khiển (Analytics Dashboard) theo dõi tỷ lệ lỗi, vị trí lỗi và hiệu suất AI/QC.

### Tính năng chính (Core Features)
- [x] **Kiểm tra & Khoanh vùng lỗi Realtime:** Nhận diện và vẽ bounding box lỗi trên 5 mặt xe từ luồng camera.
- [x] **Phân loại Trạng thái Tự động (PASS / FAIL / REVIEW):** Đánh giá đa ngưỡng dựa trên chất lượng ảnh (Q), độ tin cậy AI (C) và kích thước vật lý (S).
- [x] **Trợ lý QC Agent (Reasoning Assistant):** Đưa ra lập luận ngôn ngữ tự nhiên giải thích lý do cảnh báo và hỗ trợ QC kiểm tra các ca nghi ngờ.
- [x] **Duyệt & Đè kết quả HITL (Human-in-the-loop):** Cho phép QC Inspector xác nhận hoặc đè (override) quyết định AI.
- [x] **Dashboard & Analytics:** Biểu đồ thống kê lỗi theo mặt, loại lỗi, ca làm việc và heatmap mật độ lỗi.

### User Stories
- **Là một Kiểm định viên QC**, tôi muốn xem bounding box đánh dấu vị trí lỗi trực quan trên 5 mặt xe theo thời gian thực, để phát hiện ngay vị trí khuyết tật.
- **Là một Kiểm định viên QC**, tôi muốn nhận cảnh báo `REVIEW` kèm lý do giải thích từ AI đối với các trường hợp ranh giới, để kiểm tra nhanh mà không cần rà soát lại xe đạt chuẩn.
- **Là một Kiểm định viên QC**, tôi muốn xác nhận hoặc đè kết quả của AI bằng 1 cú nhấp chuột, để lưu trữ phản hồi phục vụ cải thiện mô hình.
- **Là một Giám sát viên QC**, tôi muốn theo dõi dashboard thống kê tỷ lệ lỗi và tỷ lệ AI bị đè kết quả, để đánh giá độ tin cậy hệ thống và chất lượng dây chuyền.

### Tech Stack
- **Frontend:** Next.js / React, TypeScript, Tailwind CSS, Canvas / SVG Overlay
- **Backend:** FastAPI (Python), REST API, WebSocket / SSE
- **AI / Computer Vision:** PyTorch, ONNX Runtime / TensorRT (Vision Model), LLM / Phoenix (Agent)
- **Database & Storage:** PostgreSQL (Metadata/Logs), Redis (Realtime state/Cache), MinIO / S3 (Object Storage)
- **Agent / Orchestration:** LangGraph (Điều phối luồng: Detect $\rightarrow$ Classify $\rightarrow$ Decide $\rightarrow$ HITL)
- **Deployment & Monitor:** Cloud GPU/CPU Inference, Phoenix (AI Log & Tracing)  
- **Dataset:** Dataset ảnh lỗi mô phỏng / công khai
---

## 3. Wireframe & UI Flow

### Luồng người dùng (User Flow)
1. **Camera / Sensor Trigger** → Capture Service chụp ảnh 5 mặt xe gửi về Backend.
2. **Vision Model & Decision Engine** → Kiểm tra chất lượng ảnh ($Q \ge 70\%$), phân tích lỗi ($C, S$), trả kết quả `PASS`, `FAIL` hoặc `REVIEW`.
3. **Frontend Display** → Hiển thị trực quan 5 mặt xe kèm Bounding Box và Trạng thái.
4. **QC Action:**
   - Nếu **PASS/FAIL rõ ràng**: Hệ thống lưu log và chuyển tiếp.
   - Nếu **REVIEW / Nghi ngờ**: QC kiểm tra chi tiết hoặc hỏi **QC Agent** → Agent giải thích và đề xuất → QC đưa ra quyết định cuối cùng (`Confirm PASS` / `Confirm FAIL`).
5. **Data Sync** → Cập nhật dữ liệu vào PostgreSQL / MinIO và hiển thị lên Dashboard.

### Sơ đồ Kiến trúc & Luồng UI

#### Sơ đồ Kiến trúc Hệ thống (System Architecture Flow)
```text
[Camera 5 mặt] ──> [Vision Model + LLM Đa phương thức] ──> [LangGraph điều phối] ──> [Backend API]
                                                                                        │
                                                                                (Realtime WS/SSE)
                                                                                        │
                                                                                        ▼
[QC Workstation / Web UI] <───> [QC Agent (Reasoning)] ───────────────> [Audit & Analytics DB(S3/MinIO)]

flowchart TD
    START([START: User Access]) --> LOGIN[1. LOGIN SCREEN<br>Enter Credentials]
    LOGIN --> D1{D1: Valid Login?}
    
    D1 -- No --> LOGIN
    D1 -- Yes --> DASHBOARD[2. DASHBOARD<br>Summary & Heatmap]
    
    DASHBOARD --> INSPECT[3. INSPECTION SCREEN<br>5-Surface Inspection View]
    INSPECT --> SCAN[3.1 AI Automatic Scan<br>Trigger: PLC / Sensor]
    SCAN --> DETECT[3.2 AI Detection Logic<br>Quality Q, Confidence C, Size S]
    
    DETECT --> D2{D2: AI Certainty Level?}
    
    D2 -- PASS Certain --> RECORD_PASS[5. RECORD PASS<br>Auto Pass Session]
    D2 -- FAIL Certain --> RECORD_FAIL[5. RECORD FAIL<br>Auto Fail Session]
    D2 -- UNCERTAIN / REVIEW --> REVIEW_PANEL[6. QC REVIEW PANEL<br>Human-In-The-Loop]
    
    subgraph REVIEW_PANEL_BOX [6. QC REVIEW PANEL]
        REVIEW_PANEL --> ZOOM[6.1 Analyze Detail View & Bounding Box]
        ZOOM --> REASONING[6.2 Interpret Agent Logic & Reasoning]
        REASONING --> QUERY[6.3 Query Agent - Optional Question]
    end
    
    QUERY --> D3{D3: QC Final Decision}
    
    D3 -- Confirm FAIL --> RECORD_FAIL
    D3 -- Override PASS --> RECORD_PASS
    
    RECORD_PASS --> AUDIT[7. AUDIT LOG & DATABASE<br>Save Decisions & Feedback]
    RECORD_FAIL --> AUDIT
    
    AUDIT --> END_NODE([END: Scan Process Complete])


┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⊗ VISUAL QC AGENT   [Station: Line-01 ▼]            Welcome, CÔNG NHÂN TRẠM QC (Operator) [Logout]│
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 🔍 SEARCH (Vehicle ID / Batch)                       Status: [Status: All ▼]   [TRIGGER SCAN]    │
├──────────────────────────────────────────────────────┬───────────────────────────┬───────────────┤
│ 5-SURFACE INSPECTION VIEW                            │ DETAILED VIEW (LEFT)      │ QC DECISION   │
│ ┌──────────────────────────┐┌──────────────────────┐ │ ┌───────────────────────┐ │ ┌───────────┐ │
│ │ FRONT             🟢PASS ││ REAR          🟢PASS │ │ │                       │ │ │ CONFIRM   │ │
│ │  ┌─────────────────────┐ ││  ┌─────────────────┐ │ │ │  SELECTED SURFACE     │ │ │ PASS      │ │
│ │  │    LỖI: XƯỚC        │ ││  │    LỖI: XƯỚC    │ │ │ │  CAMERA ZOOM VIEW     │ │ │ (Override)│ │
│ │  └─────────────────────┘ ││  └─────────────────┘ │ │ │                       │ │ ├───────────┤ │
│ │ CONFIDENCE: 89% | S: 4.2mm││ CONFIDENCE: 89% | ...│ │ │   [ BOUNDING BOX ]    │ │ │ CONFIRM   │ │
│ └──────────────────────────┘└──────────────────────┘ │ │                       │ │ │ FAIL      │ │
│ ┌──────────────────────────┐┌──────────────────────┐ │ └───────────────────────┘ │ │ (Approve) │ │
│ │ LEFT           🟡REVIEW  ││ RIGHT         🟢PASS │ │ Type: Xước                │ ├───────────┤ │
│ │  ┌─────────────────────┐ ││  ┌─────────────────┐ │ │ Confidence: 0.89          │ │ SEND TO   │ │
│ │  │    LỖI: XƯỚC        │ ││  │    LỖI: XƯỚC    │ │ │ Size: 4.2mm               │ │ REVIEW    │ │
│ │  └─────────────────────┘ ││  └─────────────────┘ │ │ Zone: Critical            │ │ QUEUE     │ │
│ └──────────────────────────┘└──────────────────────┘ ├───────────────────────────┤ ├───────────┤ │
│ ┌──────────────────────────┐                         │ AGENT LOGIC & REASONING   │ │ ASK AGENT │ │
│ │ ROOF              🟢PASS │                         │ - Image Quality (Q): 94%  │ │ (Reason)  │ │
│ └──────────────────────────┘                         │ - Confidence (C): 89%     │ └───────────┘ │
│                                                      │ - Size (S): 4.2mm (>2mm)  │ Status:       │
│                                                      │ Result: FAIL (Critical)   │ AI FAIL       │
├──────────────────────────────────────────────────────┴───────────────────────────┴───────────────┤
│ RECENT INSPECTIONS (REAL-TIME TABLE)                                                             │
│ Vehicle ID    │ Batch   │ Timestamp           │ AI Result  │ QC Decision │ Status               │
│ CAR001        │ B2401   │ 2026-08-02 10:20:31 │ REVIEW     │ FAIL        │ [Completed]          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

## 4. AI Log Setup
- [x] Đã tạo API Key trên Phoenix
- [x] Đã tích hợp Hook vào Repo
- [x] Đã test log thành công
