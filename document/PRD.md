# PRD — Visual QC Agent

## 1. Bối cảnh & Vấn đề

Trên dây chuyền sản xuất, khâu kiểm tra chất lượng (Quality Control - QC) hiện phần lớn dựa vào nhân viên kiểm tra bằng mắt thường tại trạm kiểm tra (QC inspection station). Cách làm này có các vấn đề:

- **Không nhất quán**: mỗi nhân viên có ngưỡng đánh giá lỗi khác nhau, dễ bỏ sót lỗi nhỏ hoặc quá khắt khe.
- **Chậm và tốn nhân lực**: kiểm tra thủ công từng sản phẩm giới hạn tốc độ dây chuyền.
- **Thiếu dữ liệu thống kê**: khó tổng hợp loại lỗi phổ biến, tỷ lệ lỗi theo thời gian để cải tiến quy trình sản xuất.
- **Không có bằng chứng trực quan**: khi có tranh chấp chất lượng, khó truy vết ảnh gốc + vị trí lỗi đã phát hiện.

**Mục tiêu sản phẩm**: Xây dựng **Visual QC Agent** — một AI agent nhận ảnh chụp sản phẩm từ trạm kiểm tra, tự động phát hiện, phân loại, khoanh vùng lỗi, đưa ra quyết định Pass/Fail/Cần kiểm tra thêm, đồng thời ghi nhận thống kê và sinh báo cáo theo lô, nhằm hỗ trợ (không thay thế hoàn toàn) nhân viên QC, tăng tốc độ và tính nhất quán trong kiểm tra chất lượng.

## 2. Đối tượng người dùng

| Persona | Mô tả | Nhu cầu chính |
|---|---|---|
| **QC Operator** | Nhân viên đứng trạm kiểm tra, chụp/upload ảnh sản phẩm | Kết quả nhanh (Pass/Fail/Review), giải thích lỗi rõ ràng, dễ thao tác |
| **QC Supervisor / Quản lý sản xuất** | Giám sát chất lượng theo ca/lô | Xem thống kê, báo cáo theo lô, xu hướng lỗi theo thời gian |
| **Reviewer (nhân viên kiểm tra bổ sung)** | Xử lý các case "Uncertain/Needs Human Review" | Xem ảnh + vùng khoanh lỗi + confidence, xác nhận/đảo quyết định |
| **Hệ thống mô phỏng trạm kiểm tra** | Batch job/script gửi ảnh hàng loạt | API batch upload ổn định, xử lý bất đồng bộ |

## 3. User Stories / Use Cases chính

1. **US-01**: Là QC Operator, tôi upload 1 ảnh sản phẩm vừa chụp, để nhận kết quả Pass/Fail/Review trong vài giây kèm giải thích lỗi.
2. **US-02**: Là QC Operator, tôi upload một batch ảnh (thư mục/queue mô phỏng cuối ca), để hệ thống xử lý hàng loạt và trả kết quả tổng hợp.
3. **US-03**: Là Reviewer, tôi xem danh sách sản phẩm "Needs Human Review" của một batch, xem ảnh gốc + bounding box lỗi + confidence, và xác nhận quyết định cuối cùng.
4. **US-04**: Là QC Supervisor, tôi xem thống kê Pass/Fail/Review theo batch và theo khoảng thời gian, cùng top loại lỗi phổ biến.
5. **US-05**: Là QC Supervisor, tôi tải báo cáo (JSON/CSV) của một batch để lưu trữ hoặc gửi báo cáo nội bộ.
6. **US-06**: Là hệ thống mô phỏng trạm kiểm tra, tôi gọi API để đẩy ảnh liên tục và nhận lại trạng thái xử lý (queued/processing/done) theo `batch_id`.

## 4. Yêu cầu chức năng chi tiết

### FR-1. Nhận ảnh đầu vào
- API `POST /inspections` nhận 1 ảnh (multipart/form-data), trả kết quả đồng bộ (hoặc bất đồng bộ nếu vượt ngưỡng thời gian xử lý).
- API `POST /batches` nhận nhiều ảnh cùng lúc (hoặc trỏ tới thư mục mô phỏng), tạo `batch_id`, xử lý bất đồng bộ (background task/queue).
- Ràng buộc định dạng: JPEG/PNG, kích thước tối đa (ví dụ 10MB), độ phân giải tối thiểu để đảm bảo chất lượng phát hiện lỗi.
- Validate: loại file, kích thước, ảnh hỏng/không đọc được → trả lỗi rõ ràng (400).

### FR-2. Phát hiện lỗi (Defect Detection)
- Dùng vision-capable LLM (multimodal, ví dụ GPT-4o-mini vision hoặc model vision khác cấu hình qua `.env`) để phân tích ảnh, phát hiện có/không có lỗi.
- Input: ảnh (base64/URL) + prompt mô tả taxonomy lỗi + hướng dẫn output có cấu trúc (JSON).
- Output: danh sách lỗi phát hiện được (có thể rỗng nếu sản phẩm đạt).

### FR-3. Phân loại lỗi (Defect Classification)
- Mỗi lỗi phát hiện được gán vào 1 trong các loại thuộc taxonomy chuẩn (xem mục 6).
- Mỗi lỗi có `severity` (Minor/Major/Critical) và `confidence` (0.0–1.0).

### FR-4. Khoanh vùng lỗi (Localization)
- Mỗi lỗi có bounding box `{x, y, width, height}` (tọa độ tương đối 0–1 theo % ảnh, để không phụ thuộc độ phân giải gốc) trên ảnh gốc.
- Hệ thống trả về ảnh annotate (vẽ bounding box + nhãn) hoặc dữ liệu bbox để frontend tự vẽ.

### FR-5. Quyết định Pass/Fail/Review
- Dựa trên danh sách lỗi (loại, severity, confidence), áp dụng luật quyết định (xem mục 7) để ra kết quả cuối: `PASS` / `FAIL` / `NEEDS_REVIEW`.
- Kết quả kèm lý do (rule nào được áp dụng) để minh bạch.

### FR-6. Ghi nhận thống kê
- Mỗi lần inspection được lưu vào DB (kết quả, lỗi, thời gian, batch_id).
- API thống kê: tổng số Pass/Fail/Review theo batch, theo khoảng thời gian; top N loại lỗi phổ biến; tỷ lệ lỗi (defect rate) theo thời gian (theo giờ/ngày/batch).

### FR-7. Sinh báo cáo theo lô (Batch Report)
- API tạo/lấy báo cáo cho 1 `batch_id`: tổng số ảnh, số Pass/Fail/Review, breakdown theo loại lỗi, danh sách sản phẩm Fail/Review kèm ảnh + bbox.
- Xuất định dạng JSON (mặc định) và CSV (tải về). PDF là stretch goal (out of scope MVP, xem mục 10).

## 5. Yêu cầu phi chức năng

| Hạng mục | Mục tiêu |
|---|---|
| Độ trễ xử lý 1 ảnh | ≤ 5s (P95) cho luồng đồng bộ single-image |
| Xử lý batch | Bất đồng bộ, throughput mục tiêu ≥ 20 ảnh/phút (giới hạn bởi rate limit của vision LLM) |
| Độ chính xác mong muốn | ≥ 85% accuracy trên eval set nội bộ cho quyết định Pass/Fail (đo qua `eval/`); recall lỗi Critical ưu tiên cao hơn precision (tránh bỏ sót lỗi nghiêm trọng) |
| Khả năng mở rộng | Kiến trúc cho phép thay thế vision LLM bằng specialized CV model sau này mà không đổi API/DB schema |
| Độ tin cậy | Ảnh lỗi/không parse được không làm crash toàn batch; retry tối đa N lần khi gọi LLM lỗi tạm thời |
| Khả năng truy vết | Lưu ảnh gốc + kết quả raw từ LLM để audit sau này |
| Bảo mật | Validate input ảnh nghiêm ngặt, giới hạn kích thước/tần suất upload (rate limiting) |

## 6. Taxonomy lỗi mẫu

Áp dụng cho sản phẩm điện tử/cơ khí lắp ráp tiêu biểu (có thể tùy biến theo sản phẩm thực tế của nhóm):

| Mã lỗi | Tên lỗi (VN) | Tên lỗi (EN) | Mức nghiêm trọng mặc định |
|---|---|---|---|
| SCRATCH | Trầy xước | Scratch | Minor |
| DENT | Móp méo | Dent | Major |
| DISCOLOR | Lệch màu / ố màu | Discoloration | Minor |
| MISSING_PART | Thiếu linh kiện | Missing Component | Critical |
| MISALIGNED | Lệch vị trí lắp ráp | Misalignment | Major |
| CRACK | Nứt vỡ | Crack | Critical |
| CONTAMINATION | Bụi bẩn / dị vật | Contamination/Foreign Object | Minor |
| LABEL_ERROR | Sai/thiếu nhãn, tem | Label/Marking Error | Major |
| DIMENSION_ERROR | Sai kích thước | Dimension Error | Major |
| OTHER | Lỗi khác chưa phân loại | Other/Unclassified | Major (mặc định an toàn) |

Mỗi mức nghiêm trọng ánh xạ trọng số dùng cho luật quyết định:
- **Minor** → weight 1
- **Major** → weight 3
- **Critical** → weight 10

## 7. Quy tắc quyết định Pass/Fail/Review

Tham số cấu hình (trong `.env`/`config.py`):
- `CONFIDENCE_THRESHOLD_LOW = 0.5` — dưới ngưỡng này, lỗi bị bỏ qua (không đủ tin cậy để tính) NHƯNG nếu severity=Critical thì vẫn đẩy sang Review thay vì bỏ qua hoàn toàn.
- `CONFIDENCE_THRESHOLD_HIGH = 0.8` — trên ngưỡng này, lỗi được coi là chắc chắn.
- `FAIL_SCORE_THRESHOLD = 10` — tổng weight lỗi (chỉ tính lỗi có confidence ≥ LOW) vượt ngưỡng này → FAIL.
- `REVIEW_SCORE_THRESHOLD = 3` — tổng weight nằm giữa REVIEW và FAIL, hoặc có lỗi Critical với confidence trong khoảng [LOW, HIGH) → NEEDS_REVIEW.

Logic (áp dụng tuần tự):
1. Không phát hiện lỗi nào (hoặc tất cả confidence < LOW) → **PASS**.
2. Có ít nhất 1 lỗi Critical với confidence ≥ HIGH → **FAIL** ngay (không cần cộng điểm).
3. Có lỗi Critical với confidence trong [LOW, HIGH) và không có Critical nào ≥ HIGH → **NEEDS_REVIEW**.
4. Tính `total_score = Σ(weight_i)` cho các lỗi còn lại (confidence ≥ LOW):
   - `total_score ≥ FAIL_SCORE_THRESHOLD` → **FAIL**
   - `REVIEW_SCORE_THRESHOLD ≤ total_score < FAIL_SCORE_THRESHOLD` → **NEEDS_REVIEW**
   - `total_score < REVIEW_SCORE_THRESHOLD` → **PASS**
5. Nếu bất kỳ lỗi nào có confidence < LOW nhưng severity=Critical → luôn tối thiểu **NEEDS_REVIEW** (an toàn, tránh bỏ sót).

**Ví dụ**:
- Ảnh có 1 lỗi SCRATCH (Minor, confidence 0.9) → score=1 < 3 → PASS.
- Ảnh có 2 lỗi DENT (Major, confidence 0.85 mỗi lỗi) → score=6, trong [3,10) → NEEDS_REVIEW.
- Ảnh có 1 lỗi MISSING_PART (Critical, confidence 0.92) → FAIL ngay theo rule 2.
- Ảnh có 1 lỗi CRACK (Critical, confidence 0.6) → NEEDS_REVIEW theo rule 3.

## 8. Định dạng Input/Output

**Input**:
- Ảnh: JPEG/PNG, ≤10MB, qua multipart upload (single) hoặc danh sách file/paths (batch).
- Metadata tùy chọn kèm ảnh: `product_id`, `station_id`, `timestamp`, `operator_id`.

**Output — Inspection result (JSON)**:
```json
{
  "inspection_id": "insp_abc123",
  "batch_id": "batch_20260815_01",
  "image_url": "/media/inspections/insp_abc123.jpg",
  "decision": "NEEDS_REVIEW",
  "decision_reason": "Total defect score 6.0 in review range [3,10)",
  "defects": [
    {
      "defect_type": "DENT",
      "severity": "Major",
      "confidence": 0.85,
      "bbox": {"x": 0.42, "y": 0.31, "width": 0.12, "height": 0.10}
    }
  ],
  "processed_at": "2026-08-15T09:00:00Z",
  "latency_ms": 2100
}
```

**Output — Batch report**: xem mục FR-7, xuất JSON/CSV qua `GET /batches/{batch_id}/report?format=json|csv`.

## 9. Success Metrics / Tiêu chí đánh giá

- Accuracy quyết định Pass/Fail/Review trên eval set gán nhãn thủ công ≥ 85%.
- Recall trên lỗi Critical ≥ 95% (không bỏ sót lỗi nghiêm trọng).
- P95 latency xử lý 1 ảnh ≤ 5s.
- Batch report sinh đúng, khớp số liệu 100% với dữ liệu inspection lưu trong DB (kiểm tra qua test).
- Toàn bộ 7 chức năng cốt lõi có API hoạt động, có test coverage (unit + integration).

## 10. Ràng buộc & Giả định

**Giả định**:
- Ảnh đầu vào có chất lượng đủ tốt (đủ sáng, không quá mờ) — trạm kiểm tra có điều kiện chụp ảnh chuẩn.
- Vision LLM (GPT-4o-mini vision hoặc tương đương) đủ khả năng phát hiện lỗi mẫu trong taxonomy, không cần train model CV riêng cho MVP.
- Một sản phẩm = một ảnh (MVP); mở rộng multi-angle là out of scope giai đoạn đầu.

**Ràng buộc**:
- Giới hạn bởi rate limit & chi phí gọi API LLM đa phương thức.
- Không có GPU riêng cho model CV chuyên biệt trong giai đoạn MVP (dev/demo trên máy thường + cloud LLM API).

**Out of scope (ngoài phạm vi MVP)**:
- Train/fine-tune model CV chuyên biệt (YOLO, v.v.) — có thể là hướng mở rộng tương lai.
- Tích hợp trực tiếp với camera/PLC phần cứng thật của dây chuyền — dùng mô phỏng (upload ảnh/thư mục) thay thế.
- Xuất báo cáo PDF có định dạng phức tạp (chỉ JSON/CSV cho MVP).
- Multi-tenant / phân quyền người dùng phức tạp (auth cơ bản nếu có thời gian).
- Real-time streaming video (chỉ xử lý ảnh tĩnh).

## 11. Roadmap / Milestones (mức cao)

| Milestone | Nội dung | Deliverable liên quan |
|---|---|---|
| M1 — Nền tảng | Định nghĩa state/schema, dựng graph cơ bản (preprocess → detect → decide), API upload đơn ảnh | Source code khởi tạo, ARCHITECTURE.md |
| M2 — Core Agent | Hoàn thiện toàn bộ 6 node, taxonomy + luật quyết định, lưu DB | AI Logs, PRD hoàn chỉnh |
| M3 — Batch & Report | API batch, thống kê, report JSON/CSV | Evaluation Evidence (draft) |
| M4 — Frontend & Polish | UI xem kết quả/báo cáo, review flow | Video Demo, README |
| M5 — Demo Day | Deploy live, eval hoàn chỉnh, pitch deck | Live URL, Pitch Deck, Worklog, Journal |
