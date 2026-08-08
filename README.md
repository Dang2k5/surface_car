# Visual QC Agent — FNS Baseline MVP

Visual QC Agent là hệ thống demo kiểm tra chất lượng bề mặt thân vỏ xe tại trạm
FNS. Phiên bản hiện tại tập trung vào một baseline có thể chạy end-to-end:

```text
Ảnh kiểm tra → CV mock → LangGraph → policy QC → verify/HITL → SQLite → UI
```

Backend dùng FastAPI, Agent được điều phối bằng LangGraph, dữ liệu kết quả được
lưu trong SQLite và frontend là dashboard Next.js/React song ngữ Việt–Anh.

> Đây là bản demo kỹ thuật. Các annotation, confidence, GD&T, severity, giới hạn
> đo và phương pháp xử lý hiện là dữ liệu mô phỏng, chưa phải tiêu chuẩn được nhà
> máy phê duyệt và không được dùng để quyết định release xe sản xuất.

## 1. Trạng thái hiện tại

Baseline MVP đã có:

- 8 case có ảnh thật trong `data/train` để mô phỏng các nhánh LangGraph.
- Payload detection theo cấu trúc YOLO: class, confidence, `xyxy` bbox và metadata.
- LangGraph chạy thật với state, conditional routing, verify loop và HITL.
- Stream tiến trình từng node về giao diện bằng NDJSON.
- Rule-based policy tạo phương pháp xử lý cụ thể và lý do có thể audit.
- SQLite lưu inspection, detection, classification, decision, HITL và graph run.
- Giao diện Việt–Anh để chạy case, theo dõi node, xử lý HITL và xem lịch sử.
- API xóa lịch sử Agent mà không xóa ảnh nguồn hoặc định nghĩa case.

Chưa có trong baseline:

- YOLO/segmentation model thật.
- LLM hoặc Gemini/OpenAI API.
- GD&T, work instruction và policy production đã được nhà máy phê duyệt.
- PostgreSQL checkpointer, MinIO/S3 và Phoenix monitoring.

## 2. Mock hoạt động như thế nào?

Hệ thống hiện **không dùng LLM để nhìn ảnh** và **không phân tích pixel bằng
YOLO thật**. Mỗi ảnh demo được gắn một annotation mô phỏng trong
`backend/app/simulation_cases.py`, gồm:

- loại lỗi;
- confidence;
- bounding box;
- panel/camera;
- severity;
- profile xác minh dự kiến.

Frontend gửi `image_url` cùng `mock_detection` vào API. `MockDetector` trả payload
có contract giống adapter YOLO, sau đó LangGraph xử lý payload đó như một kết quả
CV thật. Phần orchestration, loop, checkpoint, HITL, policy và persistence đều chạy
thật; chỉ detection/verifier là mock.

## 3. Kiến trúc

```text
frontend/
  Next.js/React workstation
       │ HTTP + NDJSON stream
       ▼
backend/
  FastAPI routes + validation
       │
       ▼
agent/
  LangGraph state machine
  ├── DetectorService  → MockDetector hiện tại / YOLO adapter tương lai
  ├── VerifierService  → mock second pass / camera-model second pass tương lai
  ├── ReasoningService → deterministic formatter, không gọi LLM
  └── QCRepository     → SQLite hiện tại / PostgreSQL tương lai
       │
       ▼
data/visual_qc.db
```

## 4. LangGraph workflow

```mermaid
flowchart TD
    START --> prepare_input
    prepare_input --> detect_defect
    detect_defect --> assess_result
    assess_result -->|PASS| save_result
    assess_result -->|CONFIRMED| generate_recommendation
    assess_result -->|VERIFY| verify_defect
    assess_result -->|HITL| human_review
    verify_defect --> assess_result
    human_review --> generate_recommendation
    generate_recommendation --> save_result
    save_result --> END
```

Mermaid sinh từ graph thật có thể lấy qua `GET /agent/graph` hoặc export bằng:

```powershell
python -m scripts.export_agent_graph
```

Kết quả được lưu tại `agent_flow.mmd`; bản giải thích trực quan nằm trong
`AGENT_FLOW.md`.

### QCState

`agent/graph/state.py` định nghĩa state dùng chung giữa các node. State chứa:

- `inspection_id`, `thread_id`, `vehicle_id`;
- `image_url`, `image_paths`, `camera_id`, `panel`;
- `defect_detected`, `defect_type`, `confidence`, bbox/segmentation;
- `severity`, `decision`, `reason`, `assessment_route`;
- `verify_count`, `verify_result`, retry/error metadata;
- `human_required`, `human_decision`;
- `recommendation_code`, `recommendation`, `final_status`;
- `execution_trace` để UI hiển thị từng node.

### Trách nhiệm của node

| Node | Vai trò |
|---|---|
| `prepare_input` | Kiểm tra ảnh đầu vào và khởi tạo metadata an toàn |
| `detect_defect` | Gọi detector adapter và chuẩn hóa kết quả CV |
| `assess_result` | Áp threshold để chọn PASS, CONFIRMED, VERIFY hoặc HITL |
| `verify_defect` | Thực hiện second pass và quay lại assessment |
| `human_review` | Dừng graph bằng `interrupt()` để QC quyết định |
| `generate_recommendation` | Chọn phương pháp kiểm soát theo policy deterministic |
| `save_result` | Lưu state cuối qua repository |

### Conditional routing và loop guard

Rule baseline:

1. Không phát hiện lỗi → `PASS` → lưu kết quả.
2. Verify đã xác nhận → `CONFIRMED` → sinh recommendation.
3. Verify vẫn không rõ và `verify_count >= 2` → `HITL`.
4. Confidence `>= 0.85` → xác nhận tự động.
5. Confidence từ `0.50` đến dưới `0.85` → verify.
6. Confidence dưới `0.50` → HITL fail-safe.

Guard `verify_count >= 2` ngăn loop vô hạn.

### HITL pause/resume

`human_review` dùng `interrupt()` thật của LangGraph. Checkpoint được lưu theo
`thread_id`; khi QC xác nhận, API resume cùng thread bằng `Command(resume=...)`.

```python
from langgraph.types import Command

graph.invoke(
    Command(resume={
        "action": "APPROVE",
        "reviewer": "qc-inspector-01",
        "reason": "Confirmed under controlled lighting.",
    }),
    config={"configurable": {"thread_id": thread_id}},
)
```

Development dùng `InMemorySaver`. Kết quả cuối được lưu thêm vào SQLite. Khi
chuyển sang PostgreSQL, có thể inject `PostgresSaver` vào graph builder mà không
cần thay đổi node.

## 5. Database SQLite

Database mặc định: `data/visual_qc.db`.

| Table | Nội dung |
|---|---|
| `inspections` | Vehicle, station, ảnh nguồn và trạng thái inspection |
| `defects` | Class CV, confidence, camera, bbox và model metadata |
| `classifications` | Panel, material, GD&T mock, measurement và severity |
| `decisions` | Recommendation, route, policy refs và method steps |
| `hitl_reviews` | Reviewer, action, lý do và quyết định cuối |
| `workflow_runs` | Audit JSON của baseline workflow tương thích API cũ |
| `agent_graph_runs` | State cuối của LangGraph theo `thread_id` |

`InMemorySaver` giữ checkpoint đang chạy hoặc đang chờ HITL. SQLite giữ kết quả
cuối để History và QC Queue vẫn đọc được sau khi backend restart.

## 6. API chính

Swagger: `http://127.0.0.1:8000/docs`

### LangGraph API

| Method | Endpoint | Mục đích |
|---|---|---|
| POST | `/inspections` | Bắt đầu graph thread |
| POST | `/inspections/stream` | Chạy inspection và stream từng node |
| GET | `/inspections/{thread_id}/state` | Đọc checkpoint/state hiện tại |
| POST | `/inspections/{thread_id}/resume` | Resume HITL |
| GET | `/agent/runs` | Danh sách graph run đã lưu |
| DELETE | `/agent/runs` | Xóa trace/history, giữ nguyên ảnh và case |
| GET | `/agent/graph` | Trả Mermaid từ graph thật |

Các alias `/api/langgraph/...` và `/api/agent/...` cũng được hỗ trợ.

### Baseline/mock API

| Method | Endpoint | Mục đích |
|---|---|---|
| POST | `/api/mock/seed?reset=true` | Reset và seed 8 case có ảnh |
| GET | `/api/simulations/cases` | Lấy catalog case demo |
| POST | `/api/simulations/{case_id}/run` | Chạy case mô phỏng |
| GET | `/api/mock/yolo-detections` | Xem payload YOLO mock |
| GET | `/api/inspections` | Inspection có ảnh và Agent decision |
| GET | `/api/inspections/{id}/classifications` | Classification của inspection |
| GET | `/api/inspections/{id}/decisions` | Decision của inspection |
| GET | `/api/inspections/{id}/workflows/latest` | Workflow gần nhất |

## 7. Yêu cầu môi trường

- Git.
- Python 3.11 trở lên; khuyến nghị Python 3.11.
- Node.js 22.13 trở lên.
- npm đi kèm Node.js.
- Docker Desktop chỉ cần khi muốn chạy backend bằng container.

Kiểm tra phiên bản:

```powershell
python --version
node --version
npm --version
```

## 8. Cài đặt trên máy mới — Windows PowerShell

Clone repository và mở PowerShell tại thư mục gốc:

```powershell
git clone <repository-url>
cd P-235
Copy-Item .env.example .env
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Chạy backend:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Mở PowerShell thứ hai và chạy frontend:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Mở `http://localhost:3000`; API mặc định tại `http://127.0.0.1:8000`.

### Linux/macOS

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload
```

Trong terminal thứ hai:

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

## 9. Cấu hình môi trường

Root `.env`:

```dotenv
DATABASE_URL=sqlite:///./data/visual_qc.db
```

`frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Không cần `OPENAI_API_KEY` hoặc Gemini key cho baseline này. Không commit `.env`
hoặc `.env.local`.

## 10. Chuẩn bị và chạy demo

Seed lại dữ liệu sạch:

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/mock/seed?reset=true"
```

Kịch bản demo đề xuất:

1. Mở **Kiểm tra bằng Agent** và chọn một trong 8 ảnh.
2. Nhấn **Bắt đầu kiểm tra bằng Agent**.
3. Theo dõi `prepare_input → detect_defect → assess_result` xuất hiện từng bước.
4. Dùng case confidence cao để chứng minh nhánh recommendation tự động.
5. Dùng case confidence trung bình để chứng minh verify loop.
6. Dùng case mơ hồ để graph dừng tại HITL, sau đó QC approve/reject.
7. Mở **Lịch sử** để xem state đã lưu hoặc xóa trace demo cũ.
8. Mở `/agent/graph` để đối chiếu UI trace với LangGraph thật.

Trong Windows PowerShell, `curl` là alias của `Invoke-WebRequest`; nên dùng
`Invoke-RestMethod` hoặc gọi rõ `curl.exe`.

## 11. Kiểm thử

Backend, từ thư mục gốc và sau khi activate virtual environment:

```powershell
python -m pytest -q
python -m ruff check backend agent tests
```

Frontend:

```powershell
cd frontend
npm test
```

`npm test` thực hiện production build trước khi chạy test giao diện.

## 12. Chạy backend bằng Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Container phục vụ backend tại `http://127.0.0.1:8000`. Frontend vẫn chạy riêng
bằng `npm run dev`.

## 13. Thay mock bằng thành phần thật

### YOLO/segmentation

1. Implement `DetectorService.detect(state)` trong adapter mới.
2. Map output model sang `defect_detected`, `defect_type`, confidence, bbox hoặc
   segmentation result trong `QCState`.
3. Inject adapter vào `build_qc_graph`.
4. Giữ nguyên API, node routing, frontend và repository.

### Verifier

Thay `MockVerifier` bằng second pass sử dụng crop độ phân giải cao, camera thứ hai
hoặc model ensemble đã được phê duyệt. Adapter phải giữ contract
`verify_count/verify_result`.

### PostgreSQL checkpoint/database

Cài `langgraph-checkpoint-postgres`, khởi tạo `PostgresSaver`, chạy `setup()` một
lần và truyền checkpointer vào graph builder. Repository có thể implement lại
`QCRepository` cho PostgreSQL mà không sửa graph node.

### LLM reasoning

Baseline không cần LLM. Nếu sau này cần giải thích phức tạp, implement một
`ReasoningService` riêng và chỉ dùng cho phần diễn giải. Không giao quyền release,
safety routing hoặc tạo tự do phương pháp sửa chữa cho LLM.

## 14. Cấu trúc repository

```text
agent/                 QCState, LangGraph nodes/routes/builder và service adapters
backend/               FastAPI, SQLite schema, policy và API
frontend/              Next.js/React dashboard song ngữ
data/train/            8 ảnh dùng làm evidence demo
docs/                  policy mô phỏng và tài liệu kỹ thuật bổ sung
scripts/               công cụ export graph
tests/                 backend và LangGraph tests
AGENT_FLOW.md           sơ đồ và giải thích workflow
agent_flow.mmd          Mermaid sinh từ graph
requirements.txt        dependency Python runtime + test
docker-compose.yml      chạy backend bằng Docker
```

## 15. Troubleshooting

- `spawn EINVAL`: dùng Node.js 22.13+ và mở lại PowerShell.
- Virtual environment trỏ đến Python đã bị gỡ: xóa riêng `.venv`/`.venv-new`, tạo
  lại bằng `python -m venv .venv`, rồi cài `requirements.txt`.
- Port 8000 đang bận: chạy Uvicorn với `--port 8001` và đổi
  `NEXT_PUBLIC_API_BASE_URL` thành `http://127.0.0.1:8001`.
- UI không kết nối backend: kiểm tra `/health`, CORS và giá trị
  `NEXT_PUBLIC_API_BASE_URL`.
- Lịch sử bị cộng dồn: dùng nút xóa lịch sử hoặc gọi `DELETE /agent/runs`.
- Muốn reset toàn bộ case demo: gọi `POST /api/mock/seed?reset=true`.

Tài liệu ranh giới dữ liệu mô phỏng: `docs/SIMULATION_POLICY.md`.
