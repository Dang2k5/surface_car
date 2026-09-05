# Kiến trúc hệ thống — Visual QC Agent

## 1. Sơ đồ tổng thể (infra + luồng request)

```mermaid
graph TB
    subgraph Client
        FE[Frontend<br/>React 19 + TanStack Router/Query<br/>Vercel]
    end

    subgraph AWS["AWS ap-southeast-1"]
        CF[CloudFront CDN]
        ALB[Application Load Balancer<br/>visual-qc-alb]
        subgraph EC2["EC2 g4dn.xlarge (GPU) — Docker Compose"]
            BE[FastAPI Backend<br/>surface_car-backend-1]
            Agent[LangGraph Agent]
            YOLO[YOLO26s-seg<br/>Ultralytics — GPU inference]
        end
        S3[(S3 / MinIO<br/>Object Storage<br/>ảnh, video, evidence)]
        CW[CloudWatch<br/>metrics + logs]
    end

    subgraph Supabase
        AUTH[Supabase Auth<br/>JWT / RBAC]
        PG[(Postgres<br/>runs, policies, defect_catalog,<br/>shifts, stations)]
    end

    FE -->|HTTPS| CF --> ALB --> BE
    FE -->|login| AUTH
    BE -->|verify JWT| AUTH
    BE --> Agent
    Agent --> YOLO
    BE <-->|SQL| PG
    BE <-->|upload/read| S3
    BE -->|logs/metrics| CW
```

**Vai trò từng phần:**

| Thành phần | Nhiệm vụ |
| --- | --- |
| **Frontend (Vercel)** | UI cho QC Operator/Supervisor: upload ảnh/video, xem kết quả, xử lý hàng đợi HITL, dashboard trend. Gọi API qua CloudFront. |
| **CloudFront** | CDN đứng trước ALB — cache static, TLS, một domain public duy nhất. |
| **ALB (`visual-qc-alb`)** | Load balancer, health-check `/health`, phân phối traffic tới EC2 backend. |
| **EC2 GPU (`g4dn.xlarge`)** | Host duy nhất chạy container backend bằng Docker Compose, có GPU Tesla T4 pass-through cho YOLO. |
| **FastAPI Backend** | API layer: auth, REST endpoints (`/api/v1`, `/agent/*`), điều phối gọi LangGraph Agent, đọc/ghi Postgres và S3. |
| **YOLO26s-seg** | Model detection/segmentation (Scratch, Dent) chạy trên GPU, output bbox/mask/confidence. |
| **LangGraph Agent** | State machine điều phối toàn bộ pipeline nghiệp vụ (chi tiết ở mục 2). |
| **S3 / MinIO** | Lưu ảnh gốc, video, crop ảnh lỗi, overlay — fallback về local disk nếu chưa cấu hình S3. |
| **Supabase Auth** | Xác thực người dùng (JWT), cấp role `QC_OPERATOR`/`QC_SUPERVISOR`. |
| **Supabase Postgres** | Nguồn sự thật duy nhất: agent run state, policy catalog, defect catalog, shift/station, quality alerts. |
| **CloudWatch** | Log container (awslogs driver) + custom metric CPU/RAM/GPU/disk + ALB latency/error dashboard. |

---

## 2. Luồng LangGraph Agent (state machine xử lý 1 lần kiểm tra)

```mermaid
graph TD
    START([START]) --> prepare[prepare_input<br/>chuẩn hoá ảnh/video, camera_id, context]
    prepare --> detect[detect_defect<br/>YOLO segmentation mỗi camera<br/>+ Geometry area/centroid/orientation<br/>+ Dedup theo camera]
    detect --> assess[assess_result<br/>so khớp Policy Catalog theo defect_code<br/>→ decisive_fail / ambiguous_pairs / needs_human]

    assess -->|PASS| save[save_result]
    assess -->|CONFIRMED| gen[generate_recommendation<br/>LLM giải thích quyết định]
    assess -->|HITL| human[human_review<br/>interrupt — chờ QC Operator xử lý]

    human -->|CONTINUE| gen
    human -->|ESCALATE_TO_SUPERVISOR| sup[supervisor_review<br/>interrupt — chờ QC Supervisor duyệt]
    sup --> gen

    gen --> save[save_result<br/>ghi Postgres + trả API]
    save --> END([END])
```

**Vai trò từng node:**

| Node | Nhiệm vụ |
| --- | --- |
| `prepare_input` | Chuẩn hoá input (ảnh/video → frame), gắn `camera_id`, ngữ cảnh xe/lô/ca. |
| `detect_defect` | Chạy YOLO trên từng camera, trích geometry, dedup phát hiện trùng lặp trong cùng video (union-find spatial/temporal merge). |
| `assess_result` | Đối chiếu từng lỗi với Policy Catalog theo `defect_code`; phân loại `decisive_fail` (rõ ràng FAIL), `ambiguous_pairs` (cần LLM), `needs_human` (policy bắt buộc HITL). |
| `human_review` | Node **interrupt** — dừng graph, chờ QC Operator xem và quyết định trên UI (hàng đợi HITL). |
| `supervisor_review` | Node **interrupt** thứ hai — chỉ vào khi Operator escalate; chờ QC Supervisor duyệt/override. |
| `generate_recommendation` | Gọi LLM (Groq) sinh giải thích bằng ngôn ngữ tự nhiên cho quyết định đã chốt. |
| `save_result` | Ghi toàn bộ state (detections, decision, evidence) vào Postgres, trả kết quả cho API/UI. |

---

## 3. Luồng nghiệp vụ end-to-end (người dùng thấy gì)

```mermaid
sequenceDiagram
    participant QC as QC Operator (UI)
    participant FE as Frontend
    participant BE as Backend API
    participant AG as LangGraph Agent
    participant SUP as QC Supervisor (UI)

    QC->>FE: Upload ảnh/video 5 camera
    FE->>BE: POST /api/v1/inspect (hoặc /agent/runs)
    BE->>AG: chạy graph (prepare → detect → assess)
    alt PASS rõ ràng
        AG-->>BE: PASS + giải thích
        BE-->>FE: hiển thị kết quả ngay
    else FAIL rõ ràng
        AG-->>BE: CONFIRMED FAIL + giải thích
        BE-->>FE: hiển thị kết quả ngay
    else Cần con người
        AG->>AG: interrupt tại human_review
        BE-->>FE: case vào "Hàng đợi HITL"
        QC->>FE: mở case, xem ảnh/geometry/policy
        FE->>BE: PATCH resume (quyết định của Operator)
        opt Operator escalate
            BE->>AG: interrupt tại supervisor_review
            SUP->>FE: duyệt/override
            FE->>BE: resume với quyết định Supervisor
        end
        BE->>AG: resume graph → generate_recommendation → save_result
        AG-->>BE: kết quả cuối
        BE-->>FE: cập nhật trạng thái case
    end
```

---

## 4. Ghi chú

- Toàn bộ business logic điều phối (policy match, routing PASS/FAIL/HITL) nằm **trong LangGraph Agent**, không phải microservice riêng — xem `PRD.md` §2, §7.
- Sơ đồ trên phản ánh code hiện tại (`agent/graph/builder.py`, `docker-compose.yml`, `backend/app/auth.py`, `agent/services/object_storage.py`) tại thời điểm viết tài liệu — cập nhật lại nếu graph hoặc hạ tầng thay đổi.
