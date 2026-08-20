# Worklog — Team 235 (Visual QC Agent)

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì để phục vụ đánh giá năng suất và audit bài thi.

---

## 2026-08-16 (Khởi tạo Dự án & Hoàn thành Bộ Tài liệu Gate 1)

| Member | Task | Status | Output | Time |
|:---|:---|:---|:---|:---:|
| **Phạm Bá Huy (PM & Deploy)** | Hoàn thiện PRD v1.1, Architecture, API Contract, cấu trúc báo cáo & kế hoạch triển khai Docker | ✅ Done | `docs/PRD.md`, `ARCHITECTURE.md`, `docs/API_CONTRACT.md` | 3.5h |
| **Đào Hải Đăng (PO & Computer Vision)** | Chuẩn hóa tài liệu Gate 1, thiết kế Wireframe trạm FNS, ma trận GD&T & nghiên cứu pipeline mô hình CV (YOLOv8) | ✅ Done | Wireframe & Pipeline CV | 3.0h |
| **Lê Quốc An (DEV - Backend, Frontend & Agent)** | Khởi tạo cấu trúc Backend FastAPI, LangGraph Agent boilerplate & tích hợp AI Logging hook | ✅ Done | `src/` template, cài đặt môi trường ảo `.venv` | 2.5h |
| **Hoàng Văn Thành (DEV - Benchmark & Test Engineer)** | Nghiên cứu xây dựng bộ Benchmark dataset (MVTec AD / NEU Defect) & thiết kế kịch bản thử nghiệm đánh giá | 🔄 WIP | Framework `eval/results/report.md` & Benchmark specs | 2.0h |

**Tổng kết ngày:** Hoàn thành toàn bộ mốc tài liệu Gate 1, đồng bộ hóa kiến trúc kỹ thuật giữa CV, LangGraph, Backend, Frontend và hệ thống Benchmark. Toàn đội đã sẵn sàng bước vào Sprint 1 phát triển MVP.
