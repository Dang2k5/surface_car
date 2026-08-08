# Visual QC Agent — Project Context

## 0. Trạng thái baseline hiện tại (cập nhật mới nhất)

Baseline MVP hiện tại đã tích hợp FastAPI + SQLite + LangGraph, nhưng vẫn giữ
detector/verifier và policy ở dạng mock deterministic trước khi đưa model CV thật
vào. Output nghiệp vụ không dùng Plan A/Plan B; Agent trả phương pháp cụ thể,
reason và trạng thái routing. LangGraph chạy theo các node:

```text
prepare_input → detect_defect → assess_result
              → verify loop / HITL → generate_recommendation → save_result
```

Vòng verify có guard tối đa hai lần. Trường hợp vẫn mơ hồ sẽ pause thật bằng
LangGraph `interrupt()` và resume bằng `Command(resume=...)` trên cùng `thread_id`.
Development dùng `InMemorySaver`; kết quả cuối được lưu trong bảng SQLite
`agent_graph_runs`. Xem `AGENT_FLOW.md` và `agent/README.md`.

## 1. Vai trò của tài liệu này

Đây là tài liệu bối cảnh chính thức dành cho Codex và các thành viên phát triển dự án Visual QC Agent. Trước khi sửa code hoặc đề xuất kiến trúc, hãy đọc tài liệu này và kiểm tra trạng thái thực tế của repository.

Nếu code hiện tại khác tài liệu, không tự động giả định bên nào đúng. Hãy báo rõ sự khác biệt, giữ nguyên các thay đổi hiện có và hỏi trước nếu cần thay đổi phạm vi.

## 2. Tên và mục tiêu dự án

Tên dự án: **Visual QC Agent — Team 235**.

Đây là hệ thống hỗ trợ kiểm tra chất lượng tại trạm FNS (Finish Line) trong dây chuyền lắp ráp ô tô. Hệ thống nhận ảnh từ camera, phát hiện khuyết tật, phân loại theo kiến thức kỹ thuật và đề xuất hành động vận hành cho QC.

Giá trị cốt lõi không chỉ là phát hiện lỗi bằng Computer Vision. Computer Vision trả lời câu hỏi:

> Hệ thống nhìn thấy lỗi gì và lỗi nằm ở đâu?

Agent/Domain Knowledge Engine trả lời:

> Lỗi đó có mức độ nghiêm trọng nào, có vượt tiêu chuẩn không và xe phải được xử lý như thế nào?

## 3. Người dùng mục tiêu

- **QC Inspector:** nhân viên kiểm định tại trạm FNS.
- **QC Supervisor:** người giám sát, phê duyệt hoặc override quyết định.

## 4. Pain point nghiệp vụ

QC hiện phải kiểm tra bằng mắt nhiều hạng mục:

- Xước, móp và lỗi sơn.
- Mối hàn và đường keo.
- Stud/Nut hoặc fastener bị thiếu/sai.
- VIN và thông tin định danh.

Khi phát hiện lỗi, QC còn phải tự xác định:

- Lỗi thuộc Severity Rank nào trong PSLAWBCD?
- Vùng lỗi thuộc GD&T Group 1–5 nào?
- Tolerance cho phép là bao nhiêu?
- Chi tiết là thép thường, thép mạ hay thép dập nóng?
- Xe được buff tại chỗ, chạy thử hay phải HOLD và chuyển Rework?

Quá trình này có thể mất 3–5 phút và phụ thuộc nhiều vào kinh nghiệm, sự mệt mỏi và khả năng quan sát của nhân viên.

## 5. Mục tiêu MVP

MVP phải demo được một luồng hoàn chỉnh từ ảnh đầu vào đến quyết định xử lý.

Phạm vi MVP ưu tiên:

- Hai loại lỗi chính: `scratch` và `dent`.
- Dữ liệu ảnh và kết quả CV có thể là mock.
- Có các trạng thái `PASS`, `PLAN_A`, `PLAN_B`, `HITL_REQUIRED`.
- Có rule engine đánh giá lỗi.
- Có LangGraph điều phối `detect → classify → decide → HITL`.
- Có QC xác nhận hoặc override.
- Có lưu inspection, defect, decision và HITL review.
- Có giao diện hoặc Swagger đủ để trình diễn.

Chưa cần làm ngay trong MVP:

- Camera thật.
- MES thật.
- Đo độ sâu 3D thật.
- Tích hợp đầy đủ weld/adhesive/Stud/Nut/VIN OCR.
- Tối ưu production GPU.

## 6. Decision Matrix nghiệp vụ

### Plan A — Buffing và Test Drive

Áp dụng khi lỗi nhẹ, confidence cao, không vi phạm tolerance và không có rủi ro kết cấu.

Ví dụ:

- Scratch nông/dăm bề mặt.
- Thép thường.
- GD&T Group 2–5.
- Severity Rank C/D.

Hành động:

1. Buffing tại chỗ khoảng 3 phút.
2. QC xác nhận.
3. Cho phép xe ra sân chạy thử.

### Plan B — Hold và Rework

Áp dụng khi có rủi ro an toàn, lỗi nghiêm trọng, vượt tolerance hoặc thuộc vật liệu không được xử lý theo cách thông thường.

Ví dụ:

- Dent trên thép dập nóng.
- GD&T Group 1 vượt tolerance 0.7 mm.
- Severity Rank P/S/A.
- Lỗi sơn nghiêm trọng trên Class A surface.
- Lỗi weld, glue, Stud/Nut liên quan đến kết cấu/an toàn.

Hành động:

1. Gắn nhãn `HOLD`.
2. Cấm test drive.
3. Điều hướng xe đến Rework Shop phù hợp.
4. Ghi lại nguyên nhân và evidence.

### HITL — Human In The Loop

Bắt buộc chuyển QC/Supervisor xem xét khi:

- Confidence thấp.
- Thiếu thông tin material/GD&T/VIN.
- Actual measurement gần ngưỡng tolerance.
- Nhiều camera cho kết quả mâu thuẫn.
- Lỗi nghiêm trọng nhưng dữ liệu chưa đủ.
- QC muốn override recommendation.

Không được tự động cho test drive khi thiếu dữ liệu quan trọng.

## 7. Luồng hệ thống mục tiêu

```text
[Camera / Upload ảnh]
        ↓
[Detect]
  loại lỗi, vị trí, confidence, camera
        ↓
[Classify]
  panel, material, GD&T, measurement, severity rank
        ↓
[Validate]
  kiểm tra thiếu dữ liệu, confidence, mâu thuẫn
        ├── không đủ chắc chắn → [HITL Review]
        └── đủ dữ liệu → [Decide]
                              ├── PASS
                              ├── PLAN_A: Buff + Test Drive
                              ├── PLAN_B: Hold + Rework
                              └── HITL_REQUIRED
        ↓
[Execute / Routing]
        ↓
[Save audit log + QC report]
```

## 8. LangGraph workflow

Các node dự kiến:

- `detect_node`: gọi CV service hoặc mock detector.
- `classify_node`: phân loại lỗi và tra cứu domain data.
- `validate_node`: kiểm tra độ tin cậy và tính đầy đủ của dữ liệu.
- `decide_node`: áp dụng decision rules.
- `hitl_node`: tạm dừng workflow để QC xác nhận/override.
- `execute_node`: cập nhật trạng thái và routing.
- `report_node`: lưu kết quả và tạo log/báo cáo.

State tối thiểu:

```python
class QCState(TypedDict, total=False):
    inspection_id: str
    vin: str
    image_urls: list[str]
    detections: list[dict]
    classifications: list[dict]
    validation: dict
    decision: dict
    hitl_required: bool
    hitl_result: dict
    final_action: dict
    errors: list[str]
```

LLM không được tự bịa ra tolerance, vật liệu hoặc severity. Các giá trị kỹ thuật phải đến từ database/rule engine. LLM có thể dùng để giải thích, chuẩn hóa mô tả hoặc hỗ trợ case mơ hồ.

## 9. Kiến trúc kỹ thuật mục tiêu

- **Frontend:** Next.js/React, TypeScript, Tailwind CSS, Canvas/SVG overlay.
- **Backend:** FastAPI, REST API, WebSocket hoặc SSE.
- **CV:** PyTorch, YOLO/segmentation, ONNX Runtime/TensorRT.
- **Agent orchestration:** LangGraph.
- **Database:** PostgreSQL khi chuyển production; SQLite được dùng cho baseline local.
- **Realtime state:** Redis.
- **Image storage:** MinIO/S3.
- **Tracing:** Phoenix.

Kiến trúc dữ liệu:

```text
Camera/CV → ảnh vào MinIO/S3
         → metadata và kết quả vào PostgreSQL
         → event/state vào Redis nếu cần realtime
         → LangGraph điều phối workflow
         → FastAPI cung cấp API cho frontend
```

MinIO/S3 là object storage, không phải relational database. PostgreSQL lưu metadata, rule, decision, audit log; MinIO lưu ảnh và artifact.

## 10. Domain entities dự kiến

- `Vehicle`: VIN, model, lot, station.
- `Inspection`: một phiên kiểm tra của xe.
- `CameraImage`: ảnh, camera ID, timestamp, object-storage URL.
- `Defect`: loại lỗi, vị trí, bbox/mask, confidence.
- `Classification`: panel, material, GD&T group, tolerance, measurement, rank.
- `Decision`: recommendation, action plan, route, reason codes.
- `HITLReview`: reviewer, decision trước/sau, reason, timestamp.
- `MaterialRule`: mapping panel/model → material.
- `GDTRule`: mapping region → group/tolerance.
- `AuditLog`: mọi thay đổi và event của workflow.

## 11. API baseline hiện tại

Thư mục backend hiện tại:

```text
backend/
  requirements.txt
  README.md
  app/
    __init__.py
    database.py
    models.py
    schemas.py
    main.py
```

API hiện có:

```text
GET  /health
POST /api/mock/seed
POST /api/inspections
GET  /api/inspections
GET  /api/inspections/{inspection_id}
```

Baseline đang dùng SQLite local, mock detector/verifier, LangGraph và frontend
workstation. Chưa tích hợp model CV thật, PostgreSQL checkpointer hoặc MinIO.

## 12. Checkpoints phát triển

### CP0 — Chốt phạm vi MVP

Chốt scratch/dent, mock input, decision matrix, JSON contract.

### CP1 — FastAPI + SQLite baseline

Đã bắt đầu: health check, inspection, defect, mock seed.

### CP2 — Chuẩn hóa domain model

Bổ sung decision, image, HITL review và rule models.

### CP3 — Mock Detect

Tạo mock detector với các case scratch, dent, no defect.

### CP4 — Mock Classify

Mapping defect → panel/material/GD&T/measurement/rank.

### CP5 — Decision Engine

Rule engine độc lập, có reason codes và unit tests.

### CP6 — LangGraph

Đã hoàn thành: state, bảy node, conditional edge, verify loop, HITL interrupt,
checkpointer, repository abstraction và Mermaid export.

### CP7 — HITL API

Đã hoàn thành cho LangGraph: API pause/state/resume, approve/reject/override và
bắt buộc nhập lý do.

### CP8 — Frontend QC workstation

Đã hoàn thành cho baseline: ảnh, state, node trace, routing outcome, Mermaid và
HITL resume controls song ngữ.

### CP9 — End-to-end demo

Demo scratch nhẹ, dent nghiêm trọng và case confidence thấp.

### CP10 — CV model thật

YOLO/segmentation, model version, confidence, latency, annotation.

### CP11 — Production infrastructure

PostgreSQL, MinIO, Redis, worker, Docker Compose, WebSocket/SSE.

### CP12 — Monitoring và hardening

Phoenix, audit, metrics, retry, timeout, fallback, role-based access.

## 13. Nguyên tắc phát triển

1. Làm từng checkpoint, không nhảy thẳng vào production complexity.
2. Mỗi checkpoint phải chạy được và có tiêu chí nghiệm thu.
3. Tách CV, domain rules, orchestration và API thành các lớp độc lập.
4. Không dùng LLM thay cho rule kỹ thuật có thể kiểm chứng.
5. Luôn có fallback HITL khi dữ liệu không đủ chắc chắn.
6. Quyết định HOLD phải fail-safe.
7. Mọi quyết định phải có reason code và audit log.
8. Không hard-code tolerance thật nếu chưa có tài liệu chính thức từ nhà máy.
9. Mock data phải được đánh dấu rõ là dữ liệu giả lập.
10. Không sửa hoặc xóa code hiện có mà không kiểm tra tác động.
11. Sau mỗi thay đổi, chạy syntax check, unit test hoặc API test phù hợp.
12. Khi một yêu cầu nghiệp vụ chưa rõ, hãy nêu giả định trước khi triển khai.

## 14. Cách Codex nên làm việc

Trước mỗi task:

1. Đọc tài liệu này.
2. Kiểm tra file hiện có và trạng thái Git.
3. Xác định checkpoint đang thực hiện.
4. Nêu ngắn gọn giả định và phạm vi thay đổi.

Trong khi làm:

1. Ưu tiên thay đổi nhỏ, dễ review.
2. Không tích hợp công nghệ mới nếu checkpoint hiện tại chưa cần.
3. Viết test cho business rule quan trọng.
4. Giữ API contract ổn định.

Sau khi làm:

1. Chạy kiểm tra phù hợp.
2. Báo rõ file đã thay đổi.
3. Báo rõ cách chạy và cách demo.
4. Nêu giới hạn còn lại và checkpoint tiếp theo.

## 15. Task tiếp theo mặc định

Task tiếp theo là **CP2 — Chuẩn hóa domain model**, nhưng chỉ triển khai sau khi đã xác nhận CP1 chạy được.

Prompt khởi động cho Codex:

```text
Đọc PROJECT_CONTEXT.md và kiểm tra backend hiện tại. Chúng ta đang ở CP1 và cần triển khai CP2: chuẩn hóa domain model cho Vehicle, Inspection, CameraImage, Defect, Classification, Decision, HITLReview và AuditLog. Giữ SQLite, chưa thêm LangGraph hoặc model CV thật. Trước khi sửa code, hãy nêu kế hoạch file sẽ thay đổi và các giả định. Sau đó triển khai migration/khởi tạo database, schema Pydantic, API tối thiểu và test cho các entity mới.
```
