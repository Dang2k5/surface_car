# Visual QC Agent - Team 235

## 1. Project Brief (Tóm tắt)
- **Vấn đề (Painpoint QC):**
  - Tại trạm **FNS (Finish Line)**, kiểm định viên (QC) không chỉ căng mắt soi xước/móp/sơn mà còn phải kiểm tra đai ốc (Nut/Stud), mối hàn và thông tin VIN.
  - Khi phát hiện khuyết tật, CV truyền thống chỉ khoanh vùng (Bounding Box), QC vẫn mất 3–5 phút đắn đo: *Lỗi này thuộc Rank nào (PSLAWBCD)? Vùng này là thép dập nóng hay thép thường? Tolerance GD&T cho phép bao nhiêu (Group 1–5)? Nên cho xe chạy thử luôn hay phải Hold gấp?*
- **Giải pháp & Giá trị AI Agent:** 
  - AI Agent tích hợp **Kiến thức ngành (Domain Knowledge Engine)**: Tự động đối chiếu vị trí lỗi với bản đồ **GD&T (Group 1–5, Tolerance $0.7\text{mm} - 1.5\text{mm}$)**, loại vật liệu (Thép thường / Thép dập nóng) và xếp rank **PSLAWBCD**.
  - **Tự động ra quyết định điều hướng xe (Actionable Routing):**
    - **Phương án A (Quick Fix & Test Drive):** Lỗi nhẹ Rank C/D, thuộc vùng GD&T Group 4–5 hoặc xước dăm bề mặt $\rightarrow$ Cho phép đánh bóng (Buffing) 3 phút tại chỗ $\rightarrow$ Xuất lệnh cho xe ra sân chạy thử.
    - **Phương án B (Hold & Rework Shop):** Lỗi Rank P/S/A, hoặc móp vượt Tolerance GD&T Group 1 ($>0.7\text{mm}$), hoặc thuộc chi tiết thép dập nóng $\rightarrow$ Gắn nhãn **"HOLD"**, chuyển thẳng về trạm Rework. **CẤM CHẠY THỬ** để tránh bụi bẩn bám thêm vào vết móp/sơn gây khó xử lý.
- **Đối tượng sử dụng:** Kiểm định viên QC (QC Inspector) và Giám sát viên QC (QC Supervisor) tại dây chuyền sản xuất lắp ráp ô tô - Line HA.

---

## 2. PRD (Tài liệu Yêu cầu Sản phẩm)

### Mục tiêu (Goals)
- Tự động hóa quá trình đánh giá và ra quyết định xử lý khuyết tật tại trạm FNS Line.
- Tối ưu hóa chu kỳ kiểm tra, loại bỏ thời gian đắn đo của công nhân QC (giảm từ 3–5 phút xuống dưới 2 giây/loại lỗi).
- Áp dụng chuẩn GD&T (Group 1–5), Severity Rank (PSLAWBCD) và đặc tính vật liệu (Thép dập nóng / Thép mạ / Thép thường) để ra quyết định phân luồng chính xác.
- Tích hợp Human-In-The-Loop (HITL) cho phép công nhân xác nhận hoặc điều chỉnh quyết định trong các ca cận ranh giới.

### Ma trận Ra quyết định & Hành động (Decision & Action Matrix)

| Hạng mục Phân loại | Cấu trúc & Vật liệu | GD&T Group & Tolerance | Severity Rank | Quyết định Agent & Phương án Hành động |
| :--- | :--- | :--- | :--- | :--- |
| **Xước nông / Xước dăm** | Thép thường (Lớp sơn bóng) | Group 2–3 ($1.0\text{mm} - 1.2\text{mm}$) | **Rank C / D** | **Phương án A:** Buffing 3 phút tại chỗ $\rightarrow$ **CHO CHẠY THỬ**. |
| **Móp / Biến dạng** | Thép dập nóng (Hot Stamped Steel) | Group 1 ($0.7\text{mm}$) | **Rank A / B** | **Phương án B:** Gắn nhãn **HOLD** $\rightarrow$ Chuyển Rework đặc biệt. **CẤM CHẠY THỬ**. |
| **Lỗi mối hàn / Keo / Thiếu Stud, Nut** | Khung gầm / Framing Sub-assy | Group 1–2 ($0.7\text{mm} - 1.0\text{mm}$) | **Rank P / S** *(An toàn)* | **CRITICAL HOLD:** Dừng dây chuyền / Báo động trạm $\rightarrow$ **CẤM CHẠY THỬ**. |
| **Lỗi Sơn (Sai màu / Rỗ / Bong tróc)** | Bề mặt ngoại quan (Class A) | Group 1 ($0.7\text{mm}$) | **Rank A / B** | **Phương án B:** Gắn nhãn **HOLD** $\rightarrow$ Chuyển xưởng Sơn Rework. **CẤM CHẠY THỬ**. |

### Quy trình Kiểm tra & Tính năng Hệ thống (System Features)
1. **Kiểm tra đa công đoạn (Sub $\rightarrow$ Framing $\rightarrow$ FNS Line):**
   - **Ngoại quan & Bề mặt:** Phát hiện vết Móp, Xước, Sơn (Sai màu, bong tróc, loang màu, rỗ).
   - **Mối hàn & Keo:** Kiểm tra chất lượng đường hàn, keo kết dính.
   - **Lắp ráp & Fasteners:** Đếm và xác minh số lượng Stud, Nut.
   - **Thông tin định danh:** Kiểm tra và so khớp số VIN với hệ thống MES.
2. **Hạt nhân Lập luận Công nghiệp (Industrial Reasoning Engine):**
   - Tra cứu bản đồ GD&T (Tolerance $0.7\text{mm} - 1.5\text{mm}$ từ Group 1 đến Group 5).
   - Phân cấp mức độ nghiêm trọng theo thang Rank **PSLAWBCD**.
   - Tự động cảnh báo rủi ro kỹ thuật (ví dụ: Thép dập nóng qua xử lý nhiệt không gõ nắn lạnh được; Vết móp chưa sơn nếu ra sân chạy thử sẽ bám bụi khó Rework).
3. **Giao diện Điều hướng Luồng Xe (Actionable Routing UI):**
   - Đưa ra chỉ dẫn trực quan cho QC: **PLAN A (BUFF & TEST DRIVE)** hoặc **PLAN B (HOLD & REWORK)**.
4. **Báo cáo & Thống kê Tự động (Auto-Reporting):**
   - Truy vấn database và tự động đổ dữ liệu vào các template báo cáo QC sẵn có.

---

## 3. UI Flow & Wireframe

### Sơ đồ Luồng AI Agent (Agent Decision Workflow)

```text
[Input: 8-12 Camera tại trạm FNS] ──> CV Detect: Loại lỗi + Vị trí + Số VIN + Stud/Nut
                                                 │
                                                 ▼
                          [AGENT DOMAIN ENGINE]
                          - Tra cứu Bản đồ GD&T (Group 1-5 / Tol 0.7-1.5mm)
                          - Tra cứu Loại vật liệu (Thép thường vs Dập nóng)
                          - Xếp Rank nghiêm trọng (PSLAWBCD)
                                                 │
                   ┌─────────────────────────────┴─────────────────────────────┐
                   ▼                                                           ▼
      【Lỗi nhẹ: Rank C/D | Tol OK】                              【Lỗi nặng: Rank P/S/A | Lỗi GD&T】
                   │                                                           │
                   ▼                                                           ▼
         【PHƯƠNG ÁN A (BUFFING)】                                    【PHƯƠNG ÁN B (HOLD)】
   - Đánh bóng 3 phút tại trạm FNS                              - Gắn nhãn "HOLD" (Giữ xe)
   - Lệnh: XUẤT XANH -> CHẠY THỬ                                - Lệnh: CẤM CHẠY THỬ (Tránh bám bụi)
                                                                - Điều hướng: Trạm Rework Sơn / Khung
                   │                                                           │
                   └─────────────────────────────┬─────────────────────────────┘
                                                 ▼
                                     [QC HITL Confirmation]
                                                 │
                                                 ▼
                               [Đổ dữ liệu DB vào Template Báo cáo]
```

### Layout Giao diện Trạm QC (QC Workstation Interface Wireframe)

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⊗ VISUAL QC AGENT   [Station: FNS Line - HA]             Welcome, CÔNG NHÂN TRẠM QC [Logout]     │
├──────────────────────────────────────────────────────┬───────────────────────────┬───────────────┤
│ LIVE CAMERA & CV DETECTION (FNS LINE)                │ AGENT DECISION ENGINE     │ QC ACTION     │
│ ┌──────────────────────────────────────────────────┐ │ ┌───────────────────────┐ │ ┌───────────┐ │
│ │ VIN: VN8921-2026   | Model: SUV EV               │ │ │ RECOMMENDED ACTION:   │ │ │ CONFIRM   │ │
│ │ 🎯 DEFECT DETECTED: DENT ON DOOR                 │ │ │ 🔴 PLAN B (HOLD)      │ │ │ PLAN A    │ │
│ │ - Surface Zone: Class A (GD&T Group 1)           │ │ │                       │ │ │ (Buffing) │ │
│ │ - Tolerance Allowed: 0.7mm | Actual: 1.12mm      │ │ │ 🚫 DO NOT TEST DRIVE  │ │ ├───────────┤ │
│ │ - Material: Hot Stamped Steel                    │ │ │                       │ │ │ CONFIRM   │ │
│ │ - Severity Rank: RANK A (Structural Dent)        │ │ │ Route: Send to        │ │ │ PLAN B    │ │
│ └──────────────────────────────────────────────────┘ │ │ Rework Shop (No-Goo)  │ │ │ (Hold)    │ │
│ Stud/Nut Count: 12/12 (OK) | VIN Match: YES          │ └───────────────────────┘ │ ├───────────┤ │
│ Status: FAIL (Exceeds GD&T Group 1 Tolerance)        │ REASONING LOGIC:          │ │ OVERRIDE  │ │
│                                                      │ - GD&T Group 1 Exceeded   │ │ DECISION  │ │
│                                                      │ - Hot Stamped Material    │ ├───────────┤ │
│                                                      │   cannot be cold-worked.  │ │ ASK AGENT │ │
│                                                      │ - Prevent road test dust. │ └───────────┘ │
├──────────────────────────────────────────────────────┴───────────────────────────┴───────────────┤
│ REAL-TIME VEHICLE ROUTING LOG (FNS LINE)                                                         │
│ Vehicle ID │ Defect Type │ GD&T Zone │ Severity Rank │ Recommended Action │ Status              │
│ CAR-9011   │ Scratch     │ Group 3   │ Rank C        │ Plan A (Buff 3m)   │ 🟢 Released to Test │
│ CAR-9012   │ Dent        │ Group 1   │ Rank A        │ Plan B (Hold/Paint)│ 🔴 HELD (Rework)    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Tech Stack & Integration

- **Frontend:** Next.js / React, TypeScript, Tailwind CSS, Canvas / SVG Overlay
- **Backend & APIs:** FastAPI (Python), REST API, WebSocket / SSE
- **AI & Computer Vision Engine:** PyTorch, ONNX Runtime / TensorRT (Vision Detection), LLM / Agent Reasoning Engine
- **Database & Storage:** PostgreSQL (Metadata, Logs, GD&T Standards), Redis (Realtime State), MinIO / S3 (Image & Inspection Archive)
- **Agent Orchestration:** LangGraph (Điều phối luồng: Vision Capture $\rightarrow$ GD&T & Material Lookup $\rightarrow$ Rank Decision $\rightarrow$ Action Plan $\rightarrow$ HITL)
- **Monitoring & Tracing:** Phoenix (LLM Log & Execution Tracing)

## 4. AI Log Setup
- [x] Đã tạo API Key trên Phoenix
- [x] Đã tích hợp Hook vào Repo
- [x] Đã test log thành công
