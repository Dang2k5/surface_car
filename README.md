# Visual QC Agent — FNS Baseline MVP

Visual QC Agent là hệ thống pilot kiểm tra chất lượng bề mặt thân vỏ xe tại trạm
FNS. Phiên bản hiện tại tập trung vào một baseline có thể chạy end-to-end:

```text
Ảnh/video camera chính → frame → best.pt → LangGraph → verify/HITL → Supabase → UI
```

Backend dùng FastAPI, Agent được điều phối bằng LangGraph, dữ liệu kết quả được
lưu trong Supabase PostgreSQL (SQLite dùng cho test/local fallback) và frontend là dashboard Next.js/React song ngữ Việt–Anh.

> Đây là bản pilot kỹ thuật. Kết quả CV đến từ `best.pt`; policy xử lý vẫn chưa
> phải tiêu chuẩn được nhà máy phê duyệt và không được dùng để tự động release xe
> sản xuất.

## 1. Trạng thái hiện tại

Baseline MVP đã có:

- Model pilot có thể chứa nhiều class, nhưng taxonomy vận hành chỉ tiếp nhận hai label được PRD phê duyệt: `scratch` và `dent`; class ngoài phạm vi không đi vào quyết định tự động.
- Giao diện baseline tập trung một camera chính; backend multi-camera được giữ làm khả năng mở rộng sau.
- Camera chính nhận JPEG/PNG hoặc video MP4/WebM; frontend cắt frame giữa video rồi gửi ảnh tới `best.pt`.
- Agent giám sát 10 xe gần nhất theo `defect_type + zone_name`; 3 xe liên tiếp hoặc 4/10 xe cùng nhóm lỗi sẽ kích hoạt cảnh báo công đoạn trước và đề xuất điều phối Offline Buffer.
- Màn hình `Cảnh báo lặp lỗi` gom mỗi cảnh báo thành một quy trình ngắn:
  tín hiệu lặp → mã lỗi và ảnh bằng chứng → hành động QC → điều kiện đóng cảnh báo.
  Mỗi cảnh báo hiển thị tối đa bốn ảnh đại diện, loại ảnh trùng URL và vẫn cho
  phép tải báo cáo Word.
- Policy catalog có revision, evidence bắt buộc và nguồn ISO/AIAG công khai;
  catalog mặc định là `APPROVED` trong phạm vi `DEMO_BASELINE_ONLY`, không phải
  quyền release sản xuất.
- Groq LLM là Agent phân loại mã lỗi và tạo quyết định vận hành trong giới hạn
  catalog/policy đã kiểm soát. Nếu LLM lỗi hoặc thiếu key, graph dừng tại HITL;
  không dùng rule-based fallback dưới tên Agent.
- LangGraph chạy thật với state, conditional routing, verify loop và HITL.
- Giao diện phát lại execution trace theo đúng thứ tự node sau khi model hoàn tất.
- Policy engine giới hạn tập hành động an toàn; LLM Agent phân tích evidence và
  chọn quyết định hợp lệ, sau đó toàn bộ kết quả được audit.
- SQLAlchemy repository hỗ trợ SQLite local và Supabase PostgreSQL qua `DATABASE_URL`.
- Contract mới có `POST /api/v1/inspect` và SSE `GET /api/v1/station/stream-alerts`.
- Kích thước bbox theo pixel/tỷ lệ ảnh luôn được lưu. Profile camera cố định pilot dùng `0.8 mm/pixel` để ước lượng rộng, cao và diện tích mask; kết quả mang trạng thái `PILOT_FIXED_CAMERA_ESTIMATE_NOT_QC_APPROVED`. Độ sâu vẫn để trống nếu không có depth sensor hoặc QC đo xác nhận.
- Sổ mã lỗi QC ánh xạ label CV với mã kiểm soát, số đo chiều dài và vị trí tương đối.
- Danh mục demo có 10 mã hoạt động: `SCRATCH01–05` và `DENT01–05`, được nhóm bằng `defect_family` và có `classification_rule` kiểm soát.
- Agent phân loại một `classified_defect_code` từ danh sách mã database dựa trên label, kích thước pilot, vị trí và số vùng phát hiện. Groq chỉ được chọn mã có sẵn; nếu API không hoạt động, inspection chuyển HITL.
- Khi một inspection có từ hai vùng lỗi cùng loại, state bật `similar_defect_warning` và ưu tiên mã cụm để QC kiểm tra.
- `GET /agent/status` phân biệt rõ LangGraph đang sẵn sàng, Groq đã cấu hình,
  LLM đã được gọi thành công hay đang không khả dụng. UI hiển thị trạng thái này
  ngay dưới LangGraph runtime.
- Mỗi kết quả có `agent_analysis` tổng hợp nguồn reasoning, mã lỗi, confidence, kích thước pixel/mm, vị trí, plan, quyền test drive, cảnh báo và evidence còn thiếu.
- Giao diện Việt–Anh để upload evidence, theo dõi node và xử lý HITL. Hàng đợi QC
  hiển thị ảnh, mã lỗi, confidence, kích thước/vị trí và lý do Agent chuyển
  checkpoint. Lịch sử hiển thị inspection summary có ảnh, model evidence và hành
  động cuối cùng; nhấn một bản ghi để mở toàn bộ kết quả.
- API xóa lịch sử Agent nhưng không xóa evidence đã upload.

Chi tiết luồng giao diện: [`docs/UI_WORKFLOWS.md`](docs/UI_WORKFLOWS.md).

Chưa có trong baseline:

- LLM vision trực tiếp; ảnh vẫn do `best.pt` xử lý, Groq chỉ nhận dữ liệu CV đã
  cấu trúc và policy context để suy luận.
- GD&T, work instruction và policy production đã được nhà máy phê duyệt.
- PostgreSQL checkpointer cho LangGraph, MinIO/S3 và Phoenix monitoring.
- Redis adapter cho sliding-window realtime; baseline hiện đọc 10 xe gần nhất từ Supabase.

## 2. Model pilot hoạt động như thế nào?

Frontend chỉ gửi ảnh, Vehicle ID, model xe, camera và vùng kiểm tra. Backend lưu evidence tại
`data/uploads`, chạy `best.pt`, chuẩn hóa boxes/masks của Ultralytics vào `QCState`,
sau đó LangGraph điều phối verify, HITL và recommendation. Trong pilot,
Trong chế độ Agent-first, không phát hiện lỗi sẽ đi nhánh `PASS`; label `scratch`/`dent`
được Agent tự phân loại mã và điều phối. QC chỉ nhận model error hoặc loại lỗi mới chưa
có ánh xạ trong catalog.

## 3. Kiến trúc

```text
frontend/
  Next.js/React workstation
       │ multipart upload + HTTP
       ▼
backend/
  FastAPI routes + validation
       │
       ▼
agent/
  LangGraph state machine
  ├── DetectorService  → LocalYoloSegmentationDetector(best.pt)
  ├── VerifierService  → model second pass
  ├── ReasoningService → Groq LLM Agent + schema/policy validation
  └── QCRepository     → Supabase PostgreSQL / SQLite test fallback
       │
       ▼
Supabase PostgreSQL
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
- `image_url`, `image_paths`, `camera_id`, `zone_name`;
- `defect_detected`, `defect_type`, `confidence`, bbox/segmentation;
- `detections` từ detector và `enriched_defects` sau khi Agent bổ sung ngữ cảnh;
- `severity`, `decision`, `reason`, `assessment_route`;
- `verify_count`, `verify_result`, retry/error metadata;
- `human_required`, `human_decision`, `hitl_status`;
- `recommendation_code`, `recommendation`, `final_status`; mức độ tổng thể dùng trực tiếp trường `severity`;
- `allow_test_drive` là cờ an toàn do policy quyết định;
- `execution_trace` để UI hiển thị từng node.

`recommendation_code` là tên hành động chuẩn trong state. `recommended_plan` chỉ được
sinh ở `/api/v1/inspect` để tương thích contract cũ; `final_action` đã được loại bỏ để
tránh hai trường cùng mô tả một quyết định. `vehicle_id` là khóa theo dõi bắt buộc,
`vehicle_id` là định danh vận hành duy nhất của xe trong baseline hiện tại.

### Trách nhiệm của node

| Node                      | Vai trò                                                |
| ------------------------- | ------------------------------------------------------ |
| `prepare_input`           | Kiểm tra ảnh đầu vào và khởi tạo metadata an toàn      |
| `detect_defect`           | Gọi detector adapter và chuẩn hóa kết quả CV           |
| `assess_result`           | Tự xác nhận label/mã đã biết; chỉ chuyển ngoại lệ sang HITL |
| `verify_defect`           | Node dự phòng, không dùng trong chế độ Agent-first hiện tại |
| `human_review`            | Dừng graph bằng `interrupt()` để QC quyết định         |
| `generate_recommendation` | Dùng quyết định LLM đã validate để tạo phương án vận hành |
| `save_result`             | Lưu state cuối qua repository                          |

### Conditional routing và loop guard

Rule baseline:

1. Không phát hiện lỗi → `PASS` → lưu kết quả.
2. Label đã biết và Agent chọn được mã catalog → `CONFIRMED`, không phụ thuộc confidence.
3. Model error, label mới hoặc không có mã catalog phù hợp → `HITL`.
4. `severity` là mức ảnh hưởng lấy từ mã QC: A cao, B đáng chú ý, C nhẹ; không phải confidence.

Node verify vẫn được giữ để có thể bật lại khi policy sản xuất yêu cầu second pass.

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

| Table              | Nội dung                                              |
| ------------------ | ----------------------------------------------------- |
| `agent_graph_runs` | State cuối của LangGraph theo `thread_id`             |
| `defect_catalog`   | Danh mục mã lỗi kiểm soát như `DENT01`, `SCRATCH01`   |
| `qc_decisions`     | Kết luận, điều phối, reviewer và lý do xác nhận của QC |

`InMemorySaver` giữ checkpoint đang chạy hoặc đang chờ HITL. SQLite giữ kết quả
cuối để History và QC Queue vẫn đọc được sau khi backend restart.

## 6. API chính

Swagger: `http://127.0.0.1:8000/docs`

### LangGraph API

| Method | Endpoint                          | Mục đích                                  |
| ------ | --------------------------------- | ----------------------------------------- |
| POST   | `/inspections`                    | Bắt đầu graph thread                      |
| POST   | `/inspections/stream`             | Chạy inspection và stream từng node       |
| POST   | `/inspections/from-images`         | Upload 1–5 JPEG/PNG theo camera, chạy best.pt và LangGraph |
| POST   | `/inspections/from-image`          | Tương thích upload một ảnh cũ |
| GET    | `/api/quality-alerts`              | Phân tích xu hướng lỗi lặp từ SQLite audit |
| GET    | `/api/quality-alerts/report.docx`  | Tải báo cáo cảnh báo và kế hoạch kiểm tra |
| GET    | `/api/policies`                    | Catalog policy, revision và nguồn tham chiếu |
| GET    | `/api/policies/{policy_id}`        | Chi tiết một policy và nguồn kiểm soát    |
| GET    | `/api/qc/defect-codes`             | Danh mục mã lỗi cho form QC                |
| POST   | `/api/qc/defect-codes`             | Tạo mã lỗi kiểm soát mới                   |
| GET    | `/api/qc/decisions`                | Tra cứu quyết định QC đã lưu               |
| POST   | `/api/qc/decisions`                | Ghi quyết định QC độc lập                  |
| GET    | `/inspections/{thread_id}/state`  | Đọc checkpoint/state hiện tại             |
| POST   | `/inspections/{thread_id}/resume` | Resume HITL                               |
| GET    | `/agent/runs`                     | Danh sách graph run đã lưu                |
| GET    | `/agent/runs/{thread_id}/export.json` | Tải audit JSON của một inspection     |
| GET    | `/agent/runs/export.jsonl`         | Tải toàn bộ audit dưới dạng JSONL         |
| DELETE | `/agent/runs`                     | Xóa trace/history, giữ nguyên ảnh upload  |
| GET    | `/agent/graph`                    | Trả Mermaid từ graph thật                 |

Các alias `/api/langgraph/...` và `/api/agent/...` cũng được hỗ trợ.

Khi graph dừng tại HITL, form QC yêu cầu chọn mã lỗi, severity, disposition,
reviewer và ghi rõ lý do. `POST /inspections/{thread_id}/resume` vừa tiếp tục
đúng checkpoint LangGraph vừa ghi một hàng chuẩn hóa vào `qc_decisions`; state
audit vẫn giữ bản sao `qc_decision_record` để truy xuất hai chiều.

FastAPI là lớp API, không phải database. Kiến trúc cloud là
`Next.js → FastAPI → PostgreSQL (Supabase)`. Repository dùng SQLAlchemy nên giữ
SQLite khi phát triển local và chuyển sang Supabase chỉ bằng `DATABASE_URL`.
LangGraph checkpointer vẫn là `InMemorySaver`; đây là phần persistence riêng sẽ
được chuyển sang `PostgresSaver` ở checkpoint tiếp theo.

`POST /inspections/from-images` nhận field multipart lặp lại `files` và
`camera_ids` theo cùng thứ tự, từ 1 đến 5 góc camera. Tất cả frame được YOLO
phân tích trong một lượt inspection; state trả về `camera_results` cho từng góc
và `finding_groups` để tổng hợp quan sát liên góc. Khi chưa có calibration,
nhóm quan sát từ nhiều camera được đánh dấu là ứng viên trùng lặp và vẫn giữ đủ
evidence cho QC, thay vì tự khẳng định đó là cùng một lỗi vật lý.

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
DETECTOR_PROVIDER=local_yolo
MODEL_PATH=./data/best.pt
MODEL_DEVICE=cpu
MODEL_CONFIDENCE=0.25
MODEL_IMAGE_SIZE=640
FIXED_CAMERA_CALIBRATION_ENABLED=true
CALIBRATION_MM_PER_PIXEL_X=0.8
CALIBRATION_MM_PER_PIXEL_Y=0.8
CALIBRATION_PROFILE_ID=FNS_FRONT_PILOT_1280
AUTO_PASS_ENABLED=true
CONFIRMED_THRESHOLD=0.70
VERIFY_THRESHOLD=0.40
QC_REASONING_PROVIDER=groq
GROQ_MODEL=openai/gpt-oss-20b
# GROQ_API_KEY=gsk_...
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
ENABLE_LANGSMITH_TRACING=false
LANGSMITH_TRACING=false
LANGCHAIN_TRACING_V2=false
```

Danh sách đầy đủ, phạm vi sử dụng và cấu hình local/cloud được mô tả tại
[`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md). `.env` thật chỉ tồn tại ở máy chạy
backend và không được commit. Frontend không được nhận database URL hoặc API key.

`frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## 10. Chuẩn bị và chạy demo

Kịch bản demo đề xuất:

1. Mở **Kiểm tra bằng Agent** và tải một ảnh JPEG/PNG từ máy.
2. Điền Vehicle ID, Camera ID, vùng kiểm tra và nhấn **Bắt đầu kiểm tra bằng Agent**.
3. Theo dõi `prepare_input → detect_defect → assess_result` xuất hiện từng bước.
4. Kiểm tra class, confidence, bbox, segmentation mask, model version và inference time.
5. Kết quả confidence trung bình sẽ chạy model second pass.
6. Trường hợp model lỗi hoặc loại lỗi mới chưa có ánh xạ sẽ dừng tại HITL.
7. Mở **Hàng đợi QC**, xem ảnh và lý do checkpoint rồi chọn **Mở kiểm duyệt**.
8. Mở **Cảnh báo lặp lỗi** để xem mã lỗi, ảnh của các xe liên quan và checklist
   kiểm tra khâu trước.
9. Mở **Lịch sử** để xem ảnh, mã lỗi, confidence, số đo, vị trí, quyết định cuối
   hoặc xóa trace cũ.
10. Mở `/agent/graph` để đối chiếu UI trace với LangGraph thật.

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

## 13. Mở rộng thành phần production

### YOLO/segmentation

`LocalYoloSegmentationDetector` hiện chạy `best.pt`. Khi model của team sẵn sàng,
thay đường dẫn `MODEL_PATH`; giữ nguyên contract `defect_detected`, `defect_type`,
confidence, bbox và segmentation result trong `QCState`.

### Verifier

`ModelVerifier` hiện chạy second pass bằng cùng model. Production có thể chuyển
sang crop độ phân giải cao, camera thứ hai hoặc model ensemble đã được phê duyệt,
nhưng phải giữ contract `verify_count/verify_result`.

### PostgreSQL checkpoint/database

Repository nghiệp vụ đã hỗ trợ Supabase PostgreSQL bằng SQLAlchemy + psycopg.

1. Tạo project Supabase và mở `SQL Editor`.
2. Chạy file `database/supabase_schema.sql`.
3. Trong `Connect`, lấy **Session pooler** cổng `5432` cho FastAPI chạy lâu dài.
4. URL-encode password nếu chứa ký tự đặc biệt và đặt URL trong `.env` backend:

```env
DATABASE_URL=postgresql+psycopg://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

5. Cài lại dependencies và khởi động backend. Kiểm tra `/health`,
   `/api/qc/defect-codes` và tạo một quyết định QC thử.

### Migrate dữ liệu SQLite hiện có

Script `scripts/migrate_sqlite_to_postgres.py` chỉ đọc SQLite và mặc định chạy
dry-run. Connection string được lấy từ `.env` và không được in ra terminal.

```powershell
# 1. Kiểm tra schema, kết nối và số bản ghi; chưa ghi Supabase
python scripts/migrate_sqlite_to_postgres.py

# 2. Dry-run có lọc vehicle TEST-/MOCK-/DEMO- và mock_scenario
python scripts/migrate_sqlite_to_postgres.py --exclude-test-data

# 3. Chỉ chạy sau khi đã kiểm tra kết quả dry-run
python scripts/migrate_sqlite_to_postgres.py --exclude-test-data --execute
```

Mặc định row trùng primary key được cập nhật (`--on-conflict update`). Dùng
`--on-conflict skip` nếu muốn giữ nguyên dữ liệu đã tồn tại trên Supabase. Script
migrate theo thứ tự `defect_catalog → agent_graph_runs → qc_decisions`, sau đó
đối chiếu primary key từng bảng. File `data/visual_qc.db` không bị sửa hoặc xóa.

Ảnh trong `data/uploads`, audit JSON trong `data/exports` và checkpoint
`InMemorySaver` không nằm trong SQLite nên không được script này chuyển lên cloud.

Không đặt database password trong `NEXT_PUBLIC_*` và không cho frontend kết nối
trực tiếp database. LangGraph checkpoint hiện vẫn là `InMemorySaver`; để giữ
được thread HITL sau backend restart, cài `langgraph-checkpoint-postgres`, khởi
tạo `PostgresSaver`, chạy `setup()` một lần và truyền vào graph builder.

### Groq LLM decision Agent

1. Tạo project và API key tại `https://console.groq.com/keys`.
2. Lưu key trong root `.env`; không đưa key vào frontend hoặc Git.
3. Đặt `QC_REASONING_PROVIDER=groq` rồi khởi động lại backend.
4. Kiểm tra `/agent/status`: provider là `groq`, key đã cấu hình và trạng thái
   chuyển sang `SUCCESS` sau inspection đầu tiên.

Groq phân loại mã, mức ảnh hưởng, diễn giải evidence và chọn quyết định trong tập
được policy cho phép. Backend từ chối mã, citation, action hoặc test-drive gate
ngoài context kiểm soát. Khi lời đáp lỗi/không hợp lệ, graph chuyển HITL thay vì
giả lập reasoning bằng rule. Chi tiết governance: `docs/POLICY_GOVERNANCE.md`.

## 14. Cấu trúc repository

```text
agent/                 QCState, LangGraph nodes/routes/builder và service adapters
backend/               FastAPI, SQLite repository, quality alerts và API
frontend/              Next.js/React dashboard song ngữ
data/uploads/          evidence do QC tải lên (không commit)
data/best.pt           model segmentation local (không commit)
docs/                  tài liệu kỹ thuật bổ sung
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
- LangSmith trả về `403 Forbidden`: giữ `ENABLE_LANGSMITH_TRACING=false` khi chạy local.
  Chỉ bật lại sau khi cấu hình `LANGSMITH_API_KEY` và `LANGSMITH_PROJECT` hợp lệ.
