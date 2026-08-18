# Architecture Diagram — Visual QC Agent

## Luồng dữ liệu ảnh: từ trạm kiểm tra đến báo cáo

```mermaid
flowchart TD
    subgraph Station[Trạm kiểm tra QC]
        CAM[Camera / Upload thủ công]
        SIM[Script mô phỏng batch<br/>đọc thư mục ảnh]
    end

    subgraph API[FastAPI Backend]
        UP1[POST /inspections<br/>1 ảnh - đồng bộ]
        UP2[POST /batches<br/>nhiều ảnh - bất đồng bộ]
        VALID{Validate ảnh<br/>type/size/readable}
    end

    subgraph AgentPipeline[LangGraph Agent Pipeline]
        PRE[preprocess_image<br/>resize, normalize, lưu file]
        DET[detect_defects<br/>gọi Vision LLM]
        CLS[classify_severity<br/>chuẩn hoá severity/weight]
        DEC[decide_pass_fail<br/>áp luật ngưỡng]
        LOG[log_stats<br/>ghi DB]
    end

    subgraph Storage[Lưu trữ]
        IMG[(Image Storage<br/>ảnh gốc + annotate)]
        DB[(DB: batches / inspections / defects / reports)]
    end

    subgraph Output[Đầu ra]
        RESULT[Inspection Result<br/>decision + defects + bbox]
        STATS[GET /stats<br/>thống kê tổng hợp]
        REPORT[GET /batches/id/report<br/>JSON / CSV]
        REVIEW[Human Review Queue<br/>NEEDS_REVIEW items]
    end

    CAM --> UP1
    SIM --> UP2
    UP1 --> VALID
    UP2 --> VALID
    VALID -->|invalid| ERR[Trả lỗi 400]
    VALID -->|valid| PRE
    PRE --> IMG
    PRE --> DET
    DET -->|lỗi gọi model| ERR2[error state -> END]
    DET --> CLS
    CLS --> DEC
    DEC -->|PASS/FAIL/NEEDS_REVIEW| LOG
    LOG --> DB
    LOG --> RESULT
    DEC -->|NEEDS_REVIEW| REVIEW
    DB --> STATS
    DB --> REPORT
    REVIEW -->|PATCH /inspections/id/review| DB
```

## Ghi chú luồng
- **Đường đồng bộ (single image)**: Station → `POST /inspections` → agent chạy hết pipeline → trả `RESULT` ngay trong response HTTP.
- **Đường bất đồng bộ (batch)**: Station/script → `POST /batches` → tạo `batch_id`, xử lý nền (BackgroundTasks) từng ảnh qua pipeline → client poll `GET /batches/{id}` cho tới `status=done` → gọi `GET /batches/{id}/report`.
- **Nhánh lỗi**: ảnh không hợp lệ hoặc lỗi gọi vision LLM đều dừng sớm ở agent, ghi `error` vào state, không đi tiếp qua các bước phân loại/quyết định, tránh ghi nhận sai lệch vào thống kê.
- **Nhánh review**: mọi kết quả `NEEDS_REVIEW` vẫn được ghi nhận vào DB như bình thường (không chặn pipeline), nhưng được đưa vào hàng đợi review riêng ở tầng ứng dụng/UI; khi Reviewer xác nhận, `PATCH /inspections/{id}/review` cập nhật lại `decision` cuối cùng trong DB.

## Xem thêm
- Chi tiết state schema, node/tool, API endpoints: [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- Yêu cầu chức năng, taxonomy lỗi, luật quyết định: [`../document/PRD.md`](../document/PRD.md)
