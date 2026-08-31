# Visual QC Workstation — UI workflows

Tài liệu này mô tả hành vi giao diện của baseline MVP tại trạm FNS. UI tập trung
vào thông tin giúp QC quyết định; dữ liệu kỹ thuật đầy đủ vẫn được giữ trong
LangGraph state và audit trace. Nguồn dữ liệu hiển thị luôn giữ provenance rõ
ràng: YOLO Segmentation (class/confidence/bbox/mask), Geometry Processor
(area/orientation/centroid), reasoning LLM (giải thích sau quyết định — không
còn bước Visual Verification bằng Multimodal LLM, xem `PRD.md` §7.3),
QC Rules + LangGraph (decision, đánh giá theo từng camera — xem `PRD.md` §7.4) —
xem `API_CONTRACT.md` và `POLICY_GOVERNANCE.md`.

## 1. Điều hướng chính

| Màn hình | Mục đích | Role tối thiểu |
|---|---|---|
| Tổng quan | Giới thiệu hệ thống, trạng thái ca và các kết quả mới nhất | `QC_OPERATOR` |
| Kiểm tra bằng Agent | Upload ảnh/video camera chính, theo dõi workflow và xem quyết định | `QC_OPERATOR` |
| Hàng đợi QC | Xử lý các LangGraph thread đang dừng tại HITL | `QC_OPERATOR` (case được phân công), `QC_SUPERVISOR` (toàn bộ) |
| Sổ mã lỗi QC | Quản lý ánh xạ label CV sang mã lỗi nghiệp vụ | `QC_OPERATOR` |
| Cảnh báo lặp lỗi | Theo dõi cụm lỗi lặp lại realtime (Sliding Window) và kiểm tra khâu trước | `QC_OPERATOR` |
| Lịch sử | Tra cứu inspection đã hoàn tất và mở lại state đầy đủ | `QC_OPERATOR` |
| Dashboard Trưởng ca | Historical Trend theo giờ/ca/lô/ngày, anomaly alert tổng hợp, override | `QC_SUPERVISOR` |

Baseline chỉ sử dụng `vehicle_id`, `vehicle_model`, `camera_id`, `zone_name` và
`lot_id`/`shift_id` (tùy chọn) làm ngữ cảnh upload. `vin_code`, `panel` và
`material` đã được loại khỏi UI và API. Đăng nhập bắt buộc trước khi vào các
màn hình trên; điều hướng ẩn/hiện theo role hiện tại (`QC_OPERATOR` vs
`QC_SUPERVISOR`) — xem `POLICY_GOVERNANCE.md`.

## 2. Kiểm tra bằng Agent

```text
Chọn ảnh/video
  → frontend cắt frame nếu input là video
  → POST /inspections/from-image (ảnh lưu vào S3/MinIO qua backend)
  → YOLO Segmentation detect/segment (mọi camera, không chỉ ảnh chính)
  → Geometry Processor trích xuất area/centroid/orientation
  → LangGraph chạy từng node (detect → classify → decide → HITL), phân loại
    và đánh giá policy độc lập cho từng camera có phát hiện
  → quyết định tự động hoặc interrupt HITL
```

Khi workflow đang chạy, khu vực Kết quả & Điều phối hiển thị live node trace.
Khi hoàn tất, kết quả vận hành thay thế trace và hiển thị:

- **original image** kèm **segmentation mask overlay** và **polygon/bounding
  region** vẽ trực tiếp trên ảnh (không chỉ số liệu bbox dạng bảng);
- **defect label** và **confidence** cạnh từng vùng lỗi;
- policy áp dụng và hành động (PASS/FAIL/HOLD).

Khi chọn một defect trên overlay, panel chi tiết hiển thị:

```text
crop image
YOLO result (class, confidence, bbox)
geometry (area_px, orientation_deg, centroid, aspect_ratio)
decision (severity, recommendation_code) — của riêng camera này, không suy diễn
  từ camera khác
explanation (reasoning LLM, sau khi có decision)
```

## 3. Hàng đợi QC

Chỉ hiển thị run có trạng thái `INTERRUPTED`. Mỗi thẻ gồm:

- ảnh gốc, crop và segmentation mask;
- mã xe và thread ID;
- loại lỗi và mã lỗi (YOLO class); nếu là lỗi mới, UI ghi rõ cần QC phân loại;
- YOLO confidence, kích thước ước tính (geometry pilot), vị trí và camera;
- lý do Agent chuyển checkpoint (interrupt reason — ví dụ: low confidence,
  missing evidence, LLM unavailable, có camera chưa phân loại được lỗi);
- trạng thái và CTA **Mở kiểm duyệt**.

QC mở case, chọn một trong các action **Confirm defect / Reject defect /
Change defect class / Request recapture**, nhập kết luận và resume graph.
Backend dùng `Command(resume=...)`; case hoàn tất sẽ rời hàng đợi và xuất hiện
trong Lịch sử. Nếu action là override quyết định cuối cùng, CTA chỉ hiển thị
cho role có quyền tương ứng (`POLICY_GOVERNANCE.md`).

## 4. Cảnh báo lặp lỗi (Sliding Window realtime)

Agent phân tích cửa sổ inspection gần nhất ($N=10$ xe) và nhóm theo loại lỗi,
vùng quan sát và camera. UI trình bày theo thứ tự:

1. Tín hiệu: loại lỗi, số lần lặp, số xe, camera và lần phát hiện gần nhất.
2. Bằng chứng trực quan: mã lỗi liên quan và tối đa bốn ảnh không trùng.
3. Hành động ngay: tối đa ba bước kiểm tra khâu trước.
4. Kết luận Agent: root cause hypothesis (nguồn nghi ngờ, không phải kết luận
   chắc chắn) và bộ phận chịu trách nhiệm.
5. Điều kiện đóng: QC ghi nhận kiểm tra và xác nhận lỗi không còn lặp lại.

UI không hiển thị routing command thô, trigger code nội bộ, bảng phân bố điều
phối hoặc các đoạn reasoning trùng nhau. Báo cáo Word vẫn tải qua
`GET /api/quality-alerts/report.docx`.

Màn hình này chỉ phục vụ **cảnh báo sớm realtime** (Sliding Window); phân tích
xu hướng dài hạn theo lot/shift/day thuộc Dashboard Trưởng ca (mục 6).

## 5. Lịch sử

Mỗi inspection đã hoàn tất được hiển thị thành một thẻ có:

- thumbnail evidence (từ object storage);
- mã xe, inspection ID và thread ID;
- loại lỗi và mã lỗi Agent phân loại;
- confidence và camera;
- kích thước pilot (geometry) và vị trí tương đối;
- hành động cuối, trạng thái và thời điểm QC xác nhận nếu có.

Nhấn thẻ để mở lại kết quả đầy đủ, bao gồm geometry, ảnh và phân loại của
từng camera có phát hiện.
Nút **Xóa lịch sử** gọi `DELETE /agent/runs`; thao tác này xóa trace/state
nhưng không xóa ảnh trên object storage.

## 6. Dashboard Trưởng ca (Historical Trend, role `QC_SUPERVISOR`)

Tách biệt hoàn toàn với mục 4 (Sliding Window realtime). Hiển thị:

- aggregation theo giờ/ca/lô/ngày (`GET /api/trend`): defects per lot,
  defects per shift, scratch rate per shift, dent rate per lot, PASS/FAIL
  rate;
- danh sách `SYSTEMIC_ANOMALY_ALERT` đã/đang mở, cho phép QC_SUPERVISOR theo
  dõi và đóng cảnh báo;
- khu vực override quyết định (nếu trong phạm vi dự án cho phép), luôn ghi
  role người thực hiện vào audit trail;
- lối vào quản lý QC Rules (chỉ đọc hoặc chỉnh sửa theo phạm vi dự án).

## 7. Responsive và trạng thái rỗng

- Desktop ưu tiên ảnh cạnh dữ liệu để QC quét nhanh nhiều case.
- Tablet chuyển facts thành hai cột.
- Mobile chuyển thẻ thành một cột, ảnh tỷ lệ 16:9 và giữ nguyên CTA chính.
- Khi thiếu ảnh, UI hiển thị thông báo rõ ràng; không dùng ảnh mock thay thế.
- Các giá trị vùng bắt đầu bằng `unknown` không được dùng làm tiêu đề cảnh báo.

## 8. Tiêu chí nghiệm thu UI

- QC nhận ra lỗi, xe ảnh hưởng và hành động tiếp theo mà không mở audit thô.
- Overlay segmentation/polygon hiển thị trực tiếp trên ảnh, không chỉ số bbox.
- Hàng đợi giải thích rõ lý do con người phải can thiệp, bao gồm cả trường hợp
  còn camera chưa phân loại được lỗi.
- Cảnh báo có đủ mã lỗi và ảnh để đối chiếu hiện tượng lặp.
- Lịch sử cho phép truy vết từ quyết định về evidence, geometry và LangGraph
  thread.
- Điều hướng và action tôn trọng RBAC (`QC_OPERATOR` vs `QC_SUPERVISOR`).
- Giao diện Việt–Anh không làm thay đổi dữ liệu hoặc trạng thái workflow.
