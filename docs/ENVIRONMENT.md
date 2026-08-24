# Environment configuration

Visual QC Agent sử dụng hai phạm vi biến môi trường độc lập:

- root `.env`: FastAPI, model, LangGraph, database, object storage và server-side integrations;
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
| `DATABASE_URL` | *(bắt buộc)* | PostgreSQL/Supabase — lưu inspection metadata, decision, history, lot/shift, alert (không lưu binary ảnh). Backend raise lỗi ngay lúc khởi động nếu thiếu hoặc không phải URL PostgreSQL — không còn fallback SQLite |
| `DATABASE_SCHEMA` | rỗng | Chỉ dùng cho test (`tests/conftest.py` tự set) — cô lập mỗi lần chạy test trong 1 schema PostgreSQL riêng trên cùng project Supabase, không đụng dữ liệu thật. Không set thủ công khi chạy backend |

Supabase sử dụng Session pooler và driver psycopg:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

Password phải được URL-encode. Không đặt URL này trong biến `NEXT_PUBLIC_*`.

### Object Storage (AWS S3)

Ảnh gốc, overlay, defect crop và segmentation mask không lưu binary trong
PostgreSQL — chúng lưu trên S3; database chỉ lưu object key
(`original_image_key`, `overlay_image_key`, `crop_image_key`,
`mask_image_key`, xem `API_CONTRACT.md` §5). Nếu `S3_ACCESS_KEY`/
`S3_SECRET_KEY` để trống, backend tự fallback về local disk (`./data/uploads`)
— chỉ dùng cho dev/demo không có AWS, không dùng cho production.

| Biến | Mặc định | Mục đích |
|---|---|---|
| `OBJECT_STORAGE_PROVIDER` | `s3` | Luôn là `s3` (AWS S3) |
| `S3_ENDPOINT` | rỗng | Để trống — chỉ dùng nếu trỏ tới một dịch vụ S3-compatible khác AWS |
| `S3_BUCKET` | `visual-qc` | Bucket chứa `inspections/<id>/original|overlay|defects|masks`, phải được tạo sẵn trên AWS |
| `S3_ACCESS_KEY` | rỗng | Secret server-side |
| `S3_SECRET_KEY` | rỗng | Secret server-side |
| `S3_REGION` | rỗng | Bắt buộc với AWS S3 |

Không đưa các biến `S3_*` vào `NEXT_PUBLIC_*`. Frontend chỉ truy cập ảnh qua
backend proxy hoặc presigned URL do backend cấp.

### Computer Vision (YOLO Segmentation)

| Biến | Mặc định | Mục đích |
|---|---|---|
| `DETECTOR_PROVIDER` | `local_yolo` | Chỉ hỗ trợ `local_yolo` — hệ thống luôn chạy model YOLO thật, không còn chế độ mock |
| `MODEL_PATH` | `./data/best.pt` | Đường dẫn model Ultralytics (YOLO Segmentation) |
| `MODEL_DEVICE` | `cpu` | `cpu`, CUDA device hoặc cấu hình Ultralytics hợp lệ |
| `MODEL_CONFIDENCE` | `0.25` | Ngưỡng detection ban đầu |
| `MODEL_IMAGE_SIZE` | `640` | Kích thước inference tối ưu cho CPU demo; tăng lên `1280` khi cần ưu tiên độ chính xác |

### Geometry Processor / Pilot camera calibration

| Biến | Mặc định | Mục đích |
|---|---|---|
| `FIXED_CAMERA_CALIBRATION_ENABLED` | `true` | Bật ước lượng mm từ camera cố định trong Geometry Processor |
| `CALIBRATION_MM_PER_PIXEL_X` | `0.8` | Hệ số pilot theo trục X |
| `CALIBRATION_MM_PER_PIXEL_Y` | `0.8` | Hệ số pilot theo trục Y |
| `CALIBRATION_PROFILE_ID` | `FNS_FRONT_PILOT_1280` | ID profile được ghi vào audit |

Các giá trị này chỉ là ước lượng demo
(`PILOT_FIXED_CAMERA_ESTIMATE_NOT_QC_APPROVED`), không phải phép đo QC được
hiệu chuẩn. `area_px`, `centroid`, `orientation_deg`, `aspect_ratio` và các
đặc trưng pixel khác được Geometry Processor tính deterministic bằng
OpenCV/NumPy độc lập với các biến calibration này.

### LangGraph reasoning (text)

Reasoning/explanation hiện dùng Groq. MVP **không còn** bước Visual
Verification bằng Multimodal LLM (node `multimodal_verify` đã bị bỏ khỏi
runtime — `PRD.md` §7.3, v1.4); các biến `VISION_LLM_*` không còn được code
đọc và **không cần khai báo**.

| Biến | Mặc định | Mục đích |
|---|---|---|
| `AUTO_PASS_ENABLED` | `true` | Cho phép nhánh PASS theo rule baseline |
| `CONFIRMED_THRESHOLD` | `0.70` | Ngưỡng confirmed trong graph |
| `VERIFY_THRESHOLD` | `0.40` | Ngưỡng verifier |
| `QC_REASONING_PROVIDER` | `groq` | `groq` cho runtime; `deterministic` chỉ dành cho test/offline diagnostics |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Model reasoning (text) tùy chọn |
| `GROQ_API_KEY` | rỗng | Secret server-side; bắt buộc khi provider là `groq` |

Thiếu `GROQ_API_KEY` hoặc LLM trả output không hợp lệ sẽ chuyển inspection
sang HITL; runtime không tạo deterministic reasoning thay thế khi provider là
`groq` (`POLICY_GOVERNANCE.md`). Trạng thái `/agent/status` cho biết LLM đã
được gọi thành công hay chưa.

### Authentication and RBAC (Supabase Auth)

Đăng nhập và session baseline dùng **Supabase Auth** (Supabase project cùng
với `DATABASE_URL` ở mục Database) — không tự xây login/JWT song song, tránh
hai cơ chế auth mâu thuẫn (xem `POLICY_GOVERNANCE.md`, `API_CONTRACT.md`
§7.7). Vai trò `QC_OPERATOR`/`QC_SUPERVISOR` không phải thuộc tính gốc của
Supabase Auth user — được lưu trong bảng `profiles` (PostgreSQL/Supabase,
`profiles.user_id` tham chiếu `auth.users.id`, cột `role`) và backend tra
cứu role này sau khi xác thực token.

| Biến | Mặc định | Mục đích |
|---|---|---|
| `SUPABASE_URL` | rỗng | URL project Supabase (dùng chung cho Auth và Database) |
| `SUPABASE_JWT_SECRET` | rỗng | Secret server-side để backend xác thực access token do Supabase Auth phát hành (JWT verify, không tự ký); bắt buộc trước khi bật kiểm tra RBAC |
| `SUPABASE_SERVICE_ROLE_KEY` | rỗng | Secret server-side, chỉ dùng cho tác vụ backend cần quyền admin (ví dụ tạo `profiles` khi user mới đăng ký lần đầu); không dùng cho request thông thường |
| `DEFAULT_QC_ROLE` | `QC_OPERATOR` | Role gán vào `profiles.role` cho tài khoản mới nếu không chỉ định; role hợp lệ: `QC_OPERATOR`, `QC_SUPERVISOR` |

Không đưa `SUPABASE_JWT_SECRET` hoặc `SUPABASE_SERVICE_ROLE_KEY` vào
frontend/`NEXT_PUBLIC_*`. Frontend dùng Supabase client SDK
(`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` — mục 2) để đăng
nhập trực tiếp với Supabase Auth và nhận access token; backend chỉ xác thực
(verify) token đó trên mỗi request ghi dữ liệu, không phát hành token riêng
(xem `API_CONTRACT.md` §7.7).

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

## 2. Frontend variables

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_SUPABASE_URL=https://PROJECT_REF.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

`NEXT_PUBLIC_SUPABASE_ANON_KEY` là public anon key theo đúng thiết kế
Supabase (an toàn để lộ ra client vì quyền truy cập dữ liệu được kiểm soát
bằng Row Level Security phía Supabase và bằng backend authorization phía
FastAPI, không dựa vào việc giấu key này). Không đưa `DATABASE_URL`,
`GROQ_API_KEY`, `VISION_LLM_API_KEY`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`,
`SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `LANGSMITH_API_KEY` hoặc
`AI_LOG_API_KEY` vào frontend.

## 3. Kiểm tra cấu hình

1. Gọi `GET /health` để kiểm tra FastAPI và database.
2. Gọi `GET /agent/status` để xem detector (YOLO Segmentation), object
   storage, LangGraph và reasoning/vision provider.
3. Gọi `GET /api/qc/defect-codes` để xác nhận database nghiệp vụ.
4. Upload một ảnh và kiểm tra: (a) object key mới xuất hiện trên
   `S3_BUCKET`/`inspections/<id>/`, (b) JSON audit được tạo trong
   `AUDIT_EXPORT_DIR`.
5. Nếu frontend không kết nối, kiểm tra `NEXT_PUBLIC_API_BASE_URL` và
   `CORS_ORIGINS`, sau đó khởi động lại cả hai process.
6. Đăng nhập thử với hai tài khoản Supabase có `profiles.role` khác nhau
   (`QC_OPERATOR`, `QC_SUPERVISOR`) để xác nhận backend xác thực đúng access
   token Supabase (`SUPABASE_JWT_SECRET`), tra cứu đúng role và điều hướng UI
   tương ứng RBAC.
