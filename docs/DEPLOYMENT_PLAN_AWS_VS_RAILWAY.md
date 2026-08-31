# So sánh triển khai Backend + Agent: AWS (GPU) vs Railway (CPU)

> Phạm vi: chỉ **backend + agent** (FastAPI + LangGraph + YOLO + Groq). Frontend
> đã chốt deploy trên **Vercel**, database đã chốt dùng **Supabase** — cả hai
> không nằm trong phạm vi so sánh này.
>
> Điều kiện tiên quyết: bản backend đưa vào so sánh này đã áp dụng fix ở
> `docs/ISSUE_REMEDIATION_PLAN.md` mục 1 — Groq chỉ còn sinh narrative, không
> còn nằm trên đường quyết định PASS/FAIL/HITL, và có `timeout=8s` — nên
> **không có rủi ro "Groq treo/lỗi → flood HITL"** trên cả hai hạ tầng bên dưới.

## Hạ tầng hiện có trong repo (áp dụng cho cả 2 phương án)

- `Dockerfile`: multi-stage, base `python:3.11-slim`, cài torch CPU wheel
  tường minh trước khi cài `requirements.txt` (dòng 12), `CMD uvicorn
  backend.app.main:app --host 0.0.0.0 --port 8000` (không có `--workers`).
- `railway.json`: `builder: DOCKERFILE`, `healthcheckPath: /health`,
  `healthcheckTimeout: 120`, tự restart khi lỗi (`restartPolicyMaxRetries: 3`).
- `MODEL_DEVICE` là env var trung tâm (`backend/app/config.py`), detector YOLO
  là **singleton khởi tạo 1 lần lúc app startup** (`backend/app/main.py`) —
  đổi CPU/GPU chỉ cần đổi env + base image, không đổi logic nghiệp vụ.

---

## Phương án 1 — AWS (GPU)

**Hạ tầng đề xuất**: 1 EC2 GPU instance (`g4dn.xlarge`, GPU T4) dùng **AWS Deep
Learning AMI** — đã cài sẵn NVIDIA driver + Docker + nvidia-container-toolkit,
giảm mạnh độ khó so với tự cài driver trên AMI thường.

**Thay đổi cần làm**:
- Dockerfile: bỏ dòng ép cài torch CPU wheel (dòng 12), cài torch bản CUDA
  tương ứng driver có sẵn trên AMI; chạy container với `--gpus all`.
- Env: `MODEL_DEVICE=cuda:0`.
- Networking: Application Load Balancer (TLS/ACM) trước EC2, health check
  `/health` (route có sẵn), Route53 domain, security group chỉ mở 443.
- HA: 1 instance là single point of failure; muốn có failover thật phải đưa
  vào Auto Scaling Group ≥2 instance sau ALB — **gấp đôi chi phí GPU**. Giai
  đoạn pilot có thể chấp nhận 1 instance + CloudWatch alarm + ASG min=max=1
  (tự thay instance khi crash, nhưng có gián đoạn vài phút).
- CI/CD: không có sẵn — phải tự dựng (build image → push ECR → SSH/SSM
  redeploy script hoặc CodeDeploy).

**Chi phí ước tính**: `g4dn.xlarge` on-demand ~0.526 USD/giờ (~380 USD/tháng
nếu chạy 24/7, chưa gồm ALB/EBS/data transfer); có thể dùng Spot để giảm
~60-70% nếu chấp nhận rủi ro bị thu hồi instance.

**Latency kỳ vọng**: YOLO segmentation trên GPU T4 điển hình ~20-80ms/lần
predict (so với ~300-1500ms trên CPU) — lợi thế lớn nhất rơi vào video nhiều
frame/nhiều camera, nơi thời gian cộng dồn theo số camera.

**Độ khó triển khai**: **Cao** — tự quản lý AMI/driver, network, IAM, patch
OS, dựng CI/CD riêng, không có git-push-to-deploy sẵn.

**Rủi ro crash/downtime**: instance đơn crash → downtime tới khi ASG thay thế
(vài phút, nếu có ASG) hoặc tới khi có người can thiệp thủ công (nếu không).

---

## Phương án 2 — Railway (CPU)

**Hạ tầng đề xuất**: dùng nguyên `Dockerfile` + `railway.json` hiện có —
builder đã là `DOCKERFILE`, healthcheck đã khớp `/health`. Push code, set env
(`DATABASE_URL` trỏ Supabase, `GROQ_API_KEY`, `S3_*`, `MODEL_DEVICE=cpu`),
Railway tự build/deploy, cấp domain HTTPS, tự restart container khi crash
(`restartPolicyMaxRetries: 3` đã cấu hình sẵn) — gần như zero-config so với
AWS.

**Scale/thông lượng**: tăng **số replica** trên Railway — mỗi replica là 1
process riêng, tự có singleton detector + lock model riêng, đứng sau load
balancer nội bộ của Railway. N replica ≈ N lần inference chạy song song thật
sự — đơn giản và rẻ hơn nhiều so với tự dựng Auto Scaling Group trên AWS.

Lưu ý khi tính số replica: route handler của FastAPI hiện là `def` đồng bộ
(không phải `async def`), nên Starlette tự chạy chúng trên threadpool nội bộ
thay vì block event loop — đúng, nhưng threadpool đó có số worker giới hạn.
Nếu số inspection đang giữ YOLO lock đồng thời vượt quá số worker đó, các
request khác (kể cả `/health`) sẽ phải xếp hàng chờ threadpool trước khi vào
được route. Vì vậy số replica nên tính theo tải đồng thời thực tế đo được, chứ
không chỉ theo CPU/RAM — 1 replica không tự động nghĩa là chịu được N request
song song không giới hạn.

**CI/CD**: tích hợp sẵn theo git push, không cần dựng thêm.

**Chi phí**: tính theo CPU/RAM thực dùng, thấp hơn nhiều so với việc luôn bật
1 GPU; phù hợp giai đoạn pilot/tải chưa lớn.

**Latency kỳ vọng**: giữ nguyên ~300-1500ms/lần predict trên CPU. Sau khi đã
bỏ Groq khỏi bước classify (rule engine thay thế) và Groq giờ chỉ optional
cho narrative, một lần inspect **ảnh đơn** ước tính rơi vào khoảng **1-3s** —
trong ngưỡng <5s. Video nhiều camera vẫn là điểm cần đo thực tế: mỗi camera
xử lý tuần tự 1 batch-predict, tổng thời gian ≈ (số camera) × (thời gian batch
của 1 camera).

**Độ khó triển khai**: **Thấp** — gần như không cần đổi hạ tầng, chỉ cần fix
Groq/HITL ở trên (đã làm) là dùng được ngay.

**Rủi ro crash/downtime**: mỗi replica độc lập — 1 replica crash không kéo
sập các replica khác; Railway tự phát hiện & restart qua healthcheck có sẵn.

---

## Bảng so sánh

| Tiêu chí | AWS (GPU, g4dn.xlarge) | Railway (CPU) |
|---|---|---|
| Độ khó triển khai | Cao — tự quản lý AMI/driver/network/CI-CD | Thấp — dùng lại Dockerfile/railway.json có sẵn |
| Latency/lần predict | ~20-80ms | ~300-1500ms |
| Latency tổng ảnh đơn (ước tính) | Dưới 1s | ~1-3s |
| Cách tăng concurrency | Auto Scaling Group nhiều instance (đắt, phức tạp) | Tăng số replica (đơn giản, rẻ hơn) |
| Chi phí chạy 24/7 | ~380 USD/tháng/instance (chưa gồm ALB, HA) | Thấp hơn nhiều, theo usage thực tế |
| Tỉ lệ crash/downtime | Downtime tới khi ASG thay instance (nếu có ASG) | Auto-restart nhanh, per-replica cô lập |
| Time-to-launch | Chậm — phải dựng hạ tầng mới từ đầu | Nhanh — gần như deploy ngay |

## Khuyến nghị

Bắt đầu với **Railway (CPU)** cho giai đoạn hiện tại/pilot: độ khó triển khai
thấp nhất, chi phí thấp, và sau khi đã tách Groq khỏi đường quyết định + thay
LLM bằng rule engine ở bước classify, latency CPU nhiều khả năng đã đủ đạt
<5s cho ảnh đơn. Chuyển sang **AWS (GPU)** khi một trong hai điều kiện sau xảy
ra, đo được bằng số liệu thật (không đoán trước):
- Latency thực đo dưới tải cho thấy CPU không đủ, đặc biệt với video nhiều
  camera/nhiều frame.
- Traffic đủ lớn để chi phí GPU cố định (24/7) rẻ hơn theo tổng số inspection
  so với việc scale ngang nhiều replica CPU trên Railway.
