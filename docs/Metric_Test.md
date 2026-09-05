# Báo cáo Test — 3 Tầng Chỉ Số (Product / System / AI Proxy)

| | |
| --- | --- |
| **Dự án** | Visual QC Agent — Team 235 (AI20K Build Phase, Cohort 3) |
| **Ngày báo cáo** | 2026-09-04 |
| **Phạm vi** | System Health (AWS CloudWatch, backend đang chạy trên EC2 GPU) + AI Proxy (kết quả huấn luyện YOLO26s-seg) |
| **Không nằm trong báo cáo này** | Product Health — xem lý do ở §1 |
| **Nguồn dữ liệu** | CloudWatch Dashboard `VisualQC-LoadTest` (namespace `VisualQC` + `AWS/ApplicationELB`); training run `runs-batch4-640/yolo26s_seg_v7_640` (`results.csv`, `args.yaml`, `weights/best.pt`) |

Tài liệu áp dụng khung 3 tầng chỉ số đo lường chuẩn cho một hệ thống AI-in-the-loop:

| Tầng | Đối tượng đọc | Trả lời câu hỏi | Trạng thái trong báo cáo này |
| --- | --- | --- | --- |
| 1. Product Health | PO / Lãnh đạo | Người dùng có thực sự dùng và hài lòng không? | **Bỏ qua** — chưa có tracking |
| 2. System Health | Kỹ sư hệ thống | Hệ thống có chạy ổn định không? | Có dữ liệu thật từ CloudWatch |
| 3. AI Proxy | Đội AI/ML | Model có dự đoán đúng không? | Có dữ liệu thật từ training run |

---

## 1. Product Health — bỏ qua (chưa có dữ liệu)

Tầng này cần một hệ thống product analytics (tương tác, tỷ lệ chấp nhận đề xuất
của agent, retention, ROI/thời gian tiết kiệm cho QC viên...). Repo hiện tại
**chưa có** event tracking hay analytics pipeline phía frontend/backend để đo
các chỉ số này — không bịa số liệu. Khi triển khai, đề xuất tối thiểu:

- **Engagement:** số phiên đăng nhập / QC viên / ca làm việc.
- **Acceptance rate:** tỷ lệ QC viên giữ nguyên kết luận AI (Auto-pass/Verify)
  so với tỷ lệ override thủ công.
- **Retention:** số QC viên còn dùng hệ thống sau tuần đầu triển khai.
- **ROI:** thời gian trung bình xử lý 1 xe trước/sau khi có trợ giúp AI.

---

## 2. System Health (đo qua AWS CloudWatch)

**Nguồn:** Dashboard `VisualQC-LoadTest` (region `ap-southeast-1`), instance
EC2 `i-0da4fa435ec1d5d6d` (`g4dn.xlarge`, khởi động 2026-09-03 19:32 UTC),
ALB `visual-qc-alb`. §2.1/2.2/2.4/2.5 đo trên cửa sổ **6 giờ idle** (health
check + traffic debug thủ công lúc dựng hạ tầng) — chỉ dùng để biết hành vi
lúc rảnh. §2.3 là **load test thật với concurrency thật** (20 kết nối song
song, 90 giây, 2,777 request) — đây là số liệu đáng tin cậy hơn cho câu hỏi
"hệ thống có ổn định dưới tải hay không". Cả hai đều **chưa bao gồm route
GPU inference thật** (`POST /api/v1/inspect`, cần auth) — xem giới hạn ở
cuối §2.3.

### 2.1 Uptime / Availability

| Chỉ số | Giá trị đo được |
| --- | --- |
| Healthy target (ALB → EC2) | 1/1 (100%), liên tục suốt cửa sổ đo |
| Unhealthy target | 0 |
| Trạng thái container | `surface_car-backend-1` — `Up ... (healthy)`, healthcheck `/health` mỗi 30s |

### 2.2 Latency (ALB `TargetResponseTime`, theo giờ)

| Khung giờ | p50 | p90 | p99 |
| --- | --- | --- | --- |
| 01:49–02:49 | 0.240 s | 0.261 s | 0.831 s |
| 02:49–03:49 | 0.246 s | 0.724 s | 1.491 s |
| 03:49–04:49 | 0.254 s | 0.804 s | 1.585 s |

p50 ổn định quanh **~0.25s**. p99 dao động 0.83–1.58s — khớp với các request
chạy inference GPU (nặng hơn nhiều so với `/health`). Chưa đủ mẫu để kết luận
SLA chính thức; cần load test có kịch bản (đồng thời nhiều ảnh) để đo p99 dưới
tải thực.

### 2.3 Load test thực tế (concurrency thật — không phải baseline idle)

Baseline §2.1–§2.2 đo lúc hệ thống gần như rảnh (chỉ có health check +
traffic debug thủ công), **không phản ánh hành vi dưới tải**. Để có số liệu
đáng tin, đã chạy load test thật bằng script Python (`httpx` +
`ThreadPoolExecutor`, không mock) nhắm vào 3 endpoint public thật của backend
(không cần auth): `/health`, `/agent/status`, `/api/quality-alerts` (endpoint
này có truy vấn Postgres qua Supabase — không phải static response).

| Tham số load test | Giá trị |
| --- | --- |
| Target | `https://daqd3jsdpjdgd.cloudfront.net` (CloudFront → ALB → EC2, đường đi giống hệt production) |
| Concurrency | 20 worker thread song song, liên tục trong 90 giây |
| Thời điểm | 2026-09-03 21:59:00 – 22:00:31 UTC |

**Kết quả đo từ phía client (round-trip đầy đủ qua CloudFront + ALB):**

| Chỉ số | Giá trị |
| --- | --- |
| Tổng request | 2,777 |
| Throughput | 30.6 req/s (sustained, 20 concurrent) |
| Lỗi (status ≥ 400 hoặc exception) | **0** |
| Latency p50 | 0.469 s |
| Latency p90 | 1.130 s |
| Latency p99 | 1.591 s |
| Latency max | 2.820 s |

**Đối chiếu server-side (ALB `TargetResponseTime`, cùng khung phút):** p50
0.122s / p90 0.777s / p99 1.262s, **1,749 request** ghi nhận tại ALB trong
phút cao điểm — chênh lệch với latency phía client chủ yếu do thời gian đi
qua CloudFront + round-trip mạng, không phải do backend xử lý chậm.

**Tài nguyên EC2 trong đúng khung load test** (so với phút liền trước, lúc
idle):

| Chỉ số | Trước test (idle) | Trong test (20 concurrent) |
| --- | --- | --- |
| CPU (cpu-total) | 1.06% | **14.62%** |
| RAM | 8.03% | 8.16% (gần như không đổi) |

**Kết luận:** ở mức 20 kết nối đồng thời / ~30 req/s, hệ thống xử lý **0 lỗi**,
CPU tăng có ý nghĩa (1%→14.6%) nhưng còn rất xa mức bão hoà, RAM không bị ảnh
hưởng. Đây là bằng chứng thật (không phải suy đoán) rằng backend chịu được
tải vừa phải ổn định. **Giới hạn của lần test này:** cả 3 endpoint đều KHÔNG
chạy inference GPU (route `POST /api/v1/inspect` yêu cầu Supabase access
token hợp lệ với role `QC_OPERATOR`/`QC_SUPERVISOR` — chưa có trong phạm vi
lần test này) — GPU Utilization trong lúc test vẫn đo được 0%. Muốn có số
liệu latency/GPU đáng tin dưới tải cho **luồng inference thật**, cần thêm
bước tạo token test hợp lệ và ảnh mẫu, nằm ngoài phạm vi lần chạy này.

### 2.4 Tỷ lệ lỗi & throughput (baseline idle 6 giờ, tổng hợp)

| Chỉ số | Giá trị |
| --- | --- |
| Tổng request (ALB) | 869 |
| HTTP 2xx | 831 |
| HTTP 4xx | 36 (**~4.1%**) |
| HTTP 5xx | 0 |

36 lỗi 4xx toàn bộ là `401 Unauthorized` trên `/api/auth/me` — nguyên nhân đã
chẩn đoán và xử lý trong phiên làm việc trước (token cũ kẹt trong
`localStorage` từ lần đăng nhập trước khi frontend/backend đồng bộ đúng
Supabase project). **0 lỗi 5xx** — không có lỗi phía backend/hệ thống trong
cửa sổ đo. (Số liệu load test thật ở §2.3 cho thấy 0 lỗi kể cả dưới tải —
36 lỗi 4xx ở đây thuộc baseline idle, không liên quan tới capacity.)

### 2.5 Tài nguyên hệ thống (CloudWatch Agent + custom GPU metric, trung bình 6h idle)

| Tài nguyên | Trung bình | Cao nhất | Ghi chú |
| --- | --- | --- | --- |
| CPU (cpu-total) | 1.24% | — | Idle, chưa có tải inference đồng thời |
| RAM | 8.17% | — | Dư địa lớn (limit container 4GB) |
| Disk (`/`) | 60.16% | — | **Cần theo dõi** — không thấp, nên dọn checkpoint/log cũ định kỳ |
| GPU Utilization (Tesla T4) | 0.0% | 0.0% | Không có request inference nào trong lúc đo |
| GPU Memory | 3.96% | 12.45% | Model + CUDA runtime load sẵn, chưa batch ảnh |

**Nhận xét:** hệ thống hiện đang **dư tài nguyên đáng kể** ở trạng thái idle
— CPU/RAM/GPU đều rất thấp. Đây là điều kiện tốt để chạy load test xác định
điểm bão hòa (giới hạn concurrent request trước khi p99 latency hoặc GPU
memory tăng vọt).

---

## 3. AI Proxy — Model Computer Vision (YOLO26s-seg)

**Nguồn:** `C:\Users\Admin\Downloads\key-buildphase\v6\640\s\runs-batch4-640\yolo26s_seg_v7_640`
(`results.csv`, `args.yaml`, `weights/best.pt`). Đây là **kết quả huấn luyện
offline**, tách biệt khỏi runtime repo theo đúng ranh giới mô tả trong
`docs/MODEL_CARD.md`. Báo cáo này bổ sung phần **"Validation metrics"** mà
`MODEL_CARD.md` hiện đang đánh dấu `TODO`.

### 3.1 Dữ liệu & cấu hình huấn luyện

| Mục | Giá trị |
| --- | --- |
| Dataset | `surface_clean-7`|
| Link | https://universe.roboflow.com/tieudongtaz/surface_clean |
| Số lượng ảnh train / val / test | 228/49/49 |
| Số lớp | 2 — `Dent`, `Scratch` |
| Kiến trúc | YOLO26s-seg (scale `s`), Ultralytics `8.4.137` |
| Tham số mô hình | 11.4M params, 37.1 GFLOPs @ 640×640 |
| Ảnh input / batch | 640×640, batch 4 |
| Epochs | 150 kế hoạch → dừng sớm epoch 130 (early stopping, `patience=30`) |
| Thời gian train | 2,162.7s (~36 phút) |
| SHA-256 checkpoint (`best.pt`) | `507777c8c563` |

### 3.2 Kết quả validation (checkpoint production `best.pt`, epoch 100)

| Metric | Box (detection) | Mask (segmentation) |
| --- | --- | --- |
| Precision | 0.6437 | 0.4728 |
| Recall | 0.5221 | 0.4071 |
| mAP50 | 0.5189 | 0.3612 |
| mAP50-95 | 0.2610 | 0.1323 |

### 3.3 Đối chiếu KPI (`PRD.md` §9)

| KPI | Mục tiêu | Box mAP50 | Mask mAP50 |
| --- | --- | --- | --- |
| mAP@0.5 | ≥ 90% | 51.9% | 36.1% |

---

## 4. Tổng kết & khuyến nghị ưu tiên

| # | Phát hiện | Khuyến nghị |
| --- | --- | --- |
| 1 | Mask mAP50 = 36.1%, cách xa KPI 90% | Cần thêm dữ liệu (đặc biệt annotation mask chất lượng cao), thử scale model lớn hơn (`m`/`l`) hoặc tăng epoch/imgsz trước khi coi model sẵn sàng production |
| 2 | Recall thấp hơn Precision đáng kể | Đánh giá lại ngưỡng `MODEL_CONFIDENCE` (hiện `0.25`) — có thể hạ để tăng recall, đánh đổi lấy precision, tuỳ khẩu vị rủi ro QC |
| 3 | Disk EC2 60% | Dọn định kỳ checkpoint/log cũ, hoặc tăng dung lượng volume trước khi đầy |
| 4 | Load test §2.3 mới phủ endpoint không-GPU (20 concurrent, 0 lỗi) | Cần thêm load test cho `POST /api/v1/inspect` (route chạy GPU thật) — đòi hỏi token QC_OPERATOR hợp lệ + ảnh mẫu, hiện ngoài phạm vi; đây là bài kiểm định capacity quan trọng nhất còn thiếu vì đây mới là traffic pattern thật của hệ thống |
| 5 | Product Health chưa có | Bổ sung analytics tối thiểu (acceptance rate, session count) trước lần triển khai pilot tiếp theo |
| 6 | Chưa xác nhận artifact đang chạy production | Đối chiếu SHA-256 `best.pt` trên EC2 (`MODEL_PATH`) với `507777c8c563` ở trên |
