# Environment configuration

Visual QC Agent sử dụng hai phạm vi biến môi trường độc lập:

- root `.env`: FastAPI, model, LangGraph, database và server-side integrations;
- `frontend/.env.local`: chỉ chứa URL công khai để frontend gọi FastAPI.

Sao chép template trước khi chạy:

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env.local
```

Không commit `.env`, `frontend/.env.local`, database password hoặc API key.

## 1. Backend variables

### Database

| Biến | Mặc định | Mục đích |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/visual_qc.db` | SQLite local hoặc PostgreSQL/Supabase |

Supabase sử dụng Session pooler và driver psycopg:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

Password phải được URL-encode. Không đặt URL này trong biến `NEXT_PUBLIC_*`.

### Computer Vision

| Biến | Mặc định | Mục đích |
|---|---|---|
| `DETECTOR_PROVIDER` | `local_yolo` | `local_yolo` cho runtime, `mock` chỉ dành cho test |
| `MODEL_PATH` | `./data/best.pt` | Đường dẫn model Ultralytics |
| `MODEL_DEVICE` | `cpu` | `cpu`, CUDA device hoặc cấu hình Ultralytics hợp lệ |
| `MODEL_CONFIDENCE` | `0.25` | Ngưỡng detection ban đầu |
| `MODEL_IMAGE_SIZE` | `640` | Kích thước inference tối ưu cho CPU demo; tăng lên `1280` khi cần ưu tiên độ chính xác |

### Pilot camera calibration

| Biến | Mặc định | Mục đích |
|---|---|---|
| `FIXED_CAMERA_CALIBRATION_ENABLED` | `true` | Bật ước lượng mm từ camera cố định |
| `CALIBRATION_MM_PER_PIXEL_X` | `0.8` | Hệ số pilot theo trục X |
| `CALIBRATION_MM_PER_PIXEL_Y` | `0.8` | Hệ số pilot theo trục Y |
| `CALIBRATION_PROFILE_ID` | `FNS_FRONT_PILOT_1280` | ID profile được ghi vào audit |

Các giá trị này chỉ là ước lượng demo, không phải phép đo QC được hiệu chuẩn.

### LangGraph and reasoning

| Biến | Mặc định | Mục đích |
|---|---|---|
| `AUTO_PASS_ENABLED` | `true` | Cho phép nhánh PASS theo rule baseline |
| `CONFIRMED_THRESHOLD` | `0.70` | Ngưỡng confirmed trong graph |
| `VERIFY_THRESHOLD` | `0.40` | Ngưỡng verifier |
| `QC_REASONING_PROVIDER` | `groq` | `groq` cho runtime; `deterministic` chỉ dành cho test/offline diagnostics |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Model reasoning tùy chọn |
| `GROQ_API_KEY` | rỗng | Secret server-side; bắt buộc khi provider là `groq` |

Thiếu Groq key hoặc LLM trả output không hợp lệ sẽ chuyển inspection sang HITL;
runtime không tạo deterministic reasoning thay thế. Trạng thái `/agent/status`
cho biết LLM đã được gọi thành công hay chưa.

### Audit export

| Biến | Mặc định | Mục đích |
|---|---|---|
| `AUDIT_AUTO_EXPORT_ENABLED` | `true` | Xuất một JSON audit sau khi lưu graph state |
| `AUDIT_EXPORT_DIR` | `./data/exports` | Thư mục artifact JSON |

### Runtime and CORS

| Biến | Mặc định | Mục đích |
|---|---|---|
| `APP_ENV` | `development` | Development tự cho phép localhost 3000/3001 |
| `APP_HOST` | `127.0.0.1` | Host dùng trong lệnh khởi động/deploy |
| `APP_PORT` | `8000` | Cổng FastAPI |
| `CORS_ORIGINS` | localhost:3000 | Danh sách origin, phân tách bằng dấu phẩy |
| `LOG_LEVEL` | `INFO` | Mức log cho runtime/deployment |

Ví dụ production phải khai báo chính xác frontend origin:

```dotenv
APP_ENV=production
CORS_ORIGINS=https://visual-qc.example.com
```

### Optional tracing and activity logs

`ENABLE_LANGSMITH_TRACING=false` là công tắc authoritative. Khi tắt, backend ép
`LANGSMITH_TRACING=false` và `LANGCHAIN_TRACING_V2=false`, tránh lỗi gửi trace
ngoài ý muốn.

`AI_LOG_SERVER`, `AI_LOG_API_KEY`, `AI_LOG_DIR` phục vụ repository hook, không
tham gia reasoning hoặc quyết định QC. `AI_LOG_DIR` mặc định là `.ai-log`.

`QC_LLM_AUTO_EXPLAIN` và `CHROMA_PERSIST_DIR` chỉ được giữ để tương thích tooling
cũ; runtime Visual QC hiện tại không đọc hai biến này.

## 2. Frontend variable

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Đây là biến duy nhất frontend cần. Không đưa `DATABASE_URL`, `GROQ_API_KEY`,
`LANGSMITH_API_KEY` hoặc `AI_LOG_API_KEY` vào frontend.

## 3. Kiểm tra cấu hình

1. Gọi `GET /health` để kiểm tra FastAPI và database.
2. Gọi `GET /agent/status` để xem detector, LangGraph và reasoning provider.
3. Gọi `GET /api/qc/defect-codes` để xác nhận database nghiệp vụ.
4. Upload một ảnh và kiểm tra JSON audit được tạo trong `AUDIT_EXPORT_DIR`.
5. Nếu frontend không kết nối, kiểm tra `NEXT_PUBLIC_API_BASE_URL` và
   `CORS_ORIGINS`, sau đó khởi động lại cả hai process.
