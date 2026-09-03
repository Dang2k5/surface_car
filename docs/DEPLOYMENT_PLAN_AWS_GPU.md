# Triển khai Backend + Agent trên AWS EC2 GPU

> Phạm vi: chỉ **backend + agent** (FastAPI + LangGraph + YOLO + Groq), chạy trên
> nhánh này (`feature_dang`) với GPU thật. Frontend deploy trên **Vercel**, database
> dùng **Supabase** — không đổi so với nhánh CPU, không nằm trong phạm vi file này.
>
> Đây là nhánh riêng cho track AWS GPU. Nhánh CPU (Railway) là một track song song
> khác, dùng `docs/ENVIRONMENT.md` với `MODEL_DEVICE=cpu` — không dùng chung
> Dockerfile với nhánh này.
>
> Điều kiện tiên quyết: bản backend đưa vào đây đã áp dụng fix ở
> `docs/ISSUE_REMEDIATION_PLAN.md` mục 1 — Groq chỉ còn sinh narrative, không còn
> nằm trên đường quyết định PASS/FAIL/HITL, và có `timeout=8s`.

## Thay đổi hạ tầng trên nhánh này

- **`Dockerfile`**: bỏ dòng ép cài torch CPU wheel. Cài `torch` từ index PyPI mặc
  định — trên Linux, wheel này tự bundle CUDA runtime libs (`nvidia-cublas-cu12`,
  `nvidia-cudnn-cu12`, ...) khớp CUDA 12.x, **không cần base image `nvidia/cuda`
  hay cài CUDA toolkit trong container**. Host (EC2) chỉ cần driver NVIDIA +
  `nvidia-container-toolkit` (có sẵn trên AWS Deep Learning AMI) để
  `docker run --gpus all` truyền GPU vào container. `HEALTHCHECK start-period`
  tăng lên `120s` (từ `90s`) vì CUDA context init + load model lên VRAM chậm hơn CPU.
- **`docker-compose.yml`**: `mem_limit`/`mem_reservation` tăng lên `4g`/`2g` (từ
  `1g`/`512m`) — CUDA runtime libs + batch frame video giữ trong RAM cần nhiều hơn.
  Thêm `deploy.resources.reservations.devices` (`driver: nvidia`) để truyền GPU
  qua `docker compose up` trên host EC2. **Chỉ chạy được trên host có GPU** — không
  dùng compose file này để dev local trên máy không có NVIDIA GPU.
- **`railway.json`**: đã xoá khỏi nhánh này — không dùng Railway ở đây.
- **`.env.example` / `docs/ENVIRONMENT.md`**: `MODEL_DEVICE=cuda:0` (mặc định của
  nhánh này, khác nhánh CPU đang giữ `cpu`).
- **`agent/services/yolo_detector.py`**: **không đổi.** `device=self.device` đã
  được truyền thẳng vào `model.predict()` từ trước — chỉ cần đổi env, không đổi code.

## Hạ tầng EC2

- **Instance**: `g4dn.xlarge` (GPU T4, 16GB VRAM), **AWS Deep Learning AMI** (đã có
  driver NVIDIA + Docker + nvidia-container-toolkit cài sẵn).
- **EBS**: 100GB gp3 tối thiểu — image + CUDA runtime libs + video tạm nặng hơn
  nhánh CPU đáng kể.
- **IAM instance profile**: `s3:GetObject`/`s3:PutObject` scoped vào đúng bucket,
  `secretsmanager:GetSecretValue` để kéo secret lúc container khởi động — **không**
  đặt secret trong user-data (đọc được qua metadata endpoint).
- **Networking**: ALB (TLS/ACM) trước EC2, health check `/health`
  (`health-check-grace-period` ≥ 180s — dài hơn Fargate CPU vì cold-start GPU
  chậm hơn), Route53 domain, security group chỉ mở 443 ra ngoài, SSH chỉ qua SSM
  (không mở port 22).
- **HA**: 1 instance trong Auto Scaling Group `min=max=1` là single point of
  failure — downtime vài phút khi ASG thay instance. Chấp nhận được cho pilot có
  người giám sát; **bắt buộc `max-size 2` trước khi vận hành 24/7 thật**, chấp
  nhận chi phí GPU tăng gấp đôi.
- **CI/CD**: không có git-push-to-deploy như Railway. Build → push ECR → AWS
  Systems Manager Run Command để pull/restart container trên instance trong ASG.
  Không dùng script stop-rm-run tuần tự cho production thật — không có rollback
  nếu image mới lỗi lúc khởi động; đổi thành pull → chạy container mới ở port tạm
  → healthcheck pass → mới dừng container cũ.

## Chi phí ước tính

`g4dn.xlarge` on-demand ~0.526 USD/giờ (~380 USD/tháng chạy 24/7, chưa gồm
ALB/EBS/data transfer). Spot giảm ~60–70% nhưng có thể bị thu hồi bất kỳ lúc nào —
chỉ dùng cho môi trường thử nghiệm, không dùng cho pilot có QC thật thao tác.

## Latency kỳ vọng

YOLO segmentation trên T4 điển hình ~20–80ms/lần `predict()` (so với ~300–1500ms
trên CPU) — **đo lại trên chính `best.pt` và ảnh thật của trạm FNS**, không tin số
ước tính này khi quyết định go-live. Lock toàn cục trong `yolo_detector.py` vẫn
còn — video nhiều camera vẫn xử lý tuần tự, GPU chỉ giảm thời gian mỗi batch chứ
không loại bỏ tính tuần tự giữa các camera.

## Rủi ro cần theo dõi riêng cho track này

- Driver/torch lệch version có thể khiến Ultralytics **âm thầm rơi về CPU** —
  luôn chạy `python -c "import torch; print(torch.cuda.is_available())"` trong
  container sau mỗi lần deploy để xác nhận.
- Không có managed OS/driver patching như Railway/Fargate — vá lỗi bảo mật EC2 +
  driver NVIDIA là việc tự làm.
- GPU utilization không có sẵn trong CloudWatch mặc định — cần cài
  `amazon-cloudwatch-agent` với plugin NVIDIA để biết GPU có thật sự được dùng
  hay phần lớn thời gian rảnh (quyết định có đáng chi phí GPU hay không).
