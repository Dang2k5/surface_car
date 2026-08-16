# Weekly Journal — Team 235 (Visual QC Agent)

> Ghi lại tiến độ hàng tuần: mục tiêu, kết quả hoàn thành, khó khăn & giải pháp, bài học kinh nghiệm theo tiêu chuẩn AI20K.

---

## Week 1: Khởi động Dự án, Thiết kế Ý tưởng & Hoàn thành Gate 1

### Mục tiêu tuần này
- [x] Chốt bài toán & giá trị khác biệt của AI Agent (Visual QC Agent chuyên sâu Xước/Lõm & Cảnh báo Bất thường Chống Dừng Line).
- [x] Hoàn thiện tài liệu Gate 1 (`Gate/gate_1.md`) và bộ tài liệu PRD v1.1, Architecture, API Contract.
- [x] Thiết lập hạ tầng AI Logging (Phoenix / AI20K Hooks) và môi trường phát triển chung.
- [x] Phân chia vai trò cụ thể trong nhóm: PM & Deploy, PO & CV, Dev Fullstack & Agent, Dev Benchmark & Test.

### Đã hoàn thành
- Viết hoàn chỉnh `Gate/gate_1.md`, `docs/PRD.md`, `ARCHITECTURE.md`, `docs/API_CONTRACT.md`, `docs/architecture_diagram.md`.
- Chuẩn hóa bộ ma trận quyết định: **Dung sai GD&T (Group 1–5)**, **Vật liệu (Thép dập nóng vs Thép thường)**, **Xếp rank (PSLAWBCD)**, **Phân luồng xe (Plan A vs Plan B)**, và **Cơ chế Sliding Buffer Chống Dừng Line**.
- Thiết lập xong Git branching strategy (`main`, `develop`) và AI Logging hooks.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
| :--- | :--- | :--- |
| Khảo sát người dùng trên diện rộng chưa có phản hồi do tính đặc thù ngành ô tô/công nghiệp B2B. | Chuyển sang nghiên cứu tài liệu tiêu chuẩn công nghiệp (Desk Research) và xây dựng bộ quy chuẩn dung sai GD&T & phân loại khuyết tật bề mặt theo thực tế nhà máy. | Có ngay ma trận ra quyết định sắc nét trong PRD mà không làm trễ tiến độ của các kỹ sư trong team. |
| Nguy cơ dàn trải quá nhiều loại lỗi làm giảm độ chính xác nhận diện. | Họp team thu hẹp phạm vi vào 2 khuyết tật cốt lõi: **Xước (Scratch)** và **Lõm/Móp (Dent)**, đồng thời bổ sung tính năng đột phá: **Phát hiện bất thường chuỗi chống dừng line**. | Tối ưu hóa độ chính xác CV ($>90\%$), định hình rõ nét năng lực lập luận và giá trị kinh tế của AI Agent. |

### Bài học
- Trong các dự án AI chuyên ngành hẹp, PM cần chủ động nắm bắt domain knowledge và unblock kỹ thuật bằng benchmark datasets thay vì ngồi đợi dữ liệu khảo sát hoàn hảo.
- Việc chốt sớm API Contract giữa CV và Agent giúp các dev có thể code độc lập song song ngay từ Sprint 1.

### Kế hoạch tuần sau (Week 2 - Gate 2 Milestone)
- [ ] **Đăng (PO & CV):** Xây dựng pipeline mô hình YOLOv8 tập trung nhận diện chuyên sâu Xước & Lõm, tính toán độ sâu móp.
- [ ] **An (Dev Fullstack & Agent):** Xây dựng LangGraph State Machine (`src/agents/`) tích hợp Node GD&T, Node Vật liệu, Node Bất thường chuỗi và API FastAPI.
- [ ] **Thành (Dev Benchmark & Test):** Chuẩn bị bộ test dataset (MVTec AD + Synthetic Defect) và viết automated test suite.
- [ ] **Huy (PM & Deploy):** Đóng gói Docker Compose ban đầu, theo dõi tiến độ sprint và hoàn thiện slide báo cáo.
