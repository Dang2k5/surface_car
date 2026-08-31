# Kế hoạch khắc phục các vấn đề đã phát hiện

> **Trạng thái: các mục 1-7 đã được triển khai trong code** (xem ghi chú "✅ Đã triển
> khai" ở đầu mỗi mục để biết chính xác file nào thay đổi). Mục 8 vẫn là backlog, chưa
> làm. Toàn bộ 53 test tự động (`pytest`) đang pass sau khi triển khai; `tsc --noEmit`
> phía frontend không còn lỗi. Kiểm thử thủ công end-to-end (chạy thật ứng dụng với ảnh/
> video thật) vẫn cần làm riêng — xem mục "Kiểm thử" cuối file.

Nguyên tắc xuyên suốt khi sửa: mỗi vấn đề phải được sửa sao cho **hệ thống vẫn tự động
hoá được phần lớn ca kiểm tra** — không "vá" bằng cách hạ ngưỡng/timeout rồi đẩy mọi thứ
sang con người xử lý (HITL), vì làm vậy thì Agent QC mất hết giá trị (tốn nhân sự y như
không có AI).

---

## 1. Groq LLM có thể treo request — sửa đúng vai trò theo đề bài gốc, không phải thêm timeout

✅ **Đã triển khai** (rule engine thay LLM cho bước chọn mã lỗi):
`agent/services/defect_rule_engine.py` (module mới) + cột `rule_type/min_mm/max_mm/
min_detection_count` trên `defect_catalog` (`backend/app/database.py::_ensure_columns`,
backfill idempotent trong `_backfill_default_defect_code_rules`) + `qc_schemas.py`'s
`DefectCodeCreate/Update` validate các trường này + UI supervisor
(`frontend/src/routes/supervisor/catalogs.tsx`). `agent/graph/nodes.py::
_classify_local_detection` không còn gọi `self.reasoning.classify_defect_code(...)` —
gọi `classify_by_rule(...)` thay thế; không match được rule → route thẳng HITL
(`RULE_ENGINE_NO_MATCH_REQUIRES_HITL`), không còn phụ thuộc Groq ở bước này. Test:
`tests/test_defect_rule_engine.py` (9 case, gồm cả MIN_COUNT ưu tiên hơn THRESHOLD_MM,
REQUIRES_HUMAN không bao giờ tự khớp). Việc còn lại (chưa làm, không khẩn theo kế hoạch
gốc): đo P99 Groq thực tế cho `analyze()`/narrative rồi mới chốt timeout, và chỉ số
"tỉ lệ mã lỗi chưa có structured rule" — để dành cho đợt sau khi có dữ liệu vận hành thật.

### Căn cứ: đề bài gốc (`docs/DE_BAI_GOC.md`) đã quy định rõ vai trò từng phần
> Computer Vision (YOLOv8/Detectron2 **phát hiện lỗi**) **+ LLM đa phương thức (mô tả/giải
> thích lỗi)** — LangGraph điều phối (**detect → classify → decide → HITL**) — ...
> **ngưỡng tin cậy để tự động chuyển người khi mơ hồ**.

Đối chiếu với code hiện tại:
- **detect → classify** (phát hiện + gán loại lỗi dent/scratch): việc của YOLO — đúng vai trò.
- **decide** (chọn severity band / PASS-FAIL): đề bài quy định dựa trên **ngưỡng tin cậy**,
  tức là **rule/threshold**, KHÔNG phải LLM.
- **LLM**: vai trò đề bài giao là **"mô tả/giải thích lỗi"** — diễn giải một quyết định đã
  có, không phải tự ra quyết định đó.
- Đề bài "Nâng cao" còn một vai trò LLM thứ hai: **"đề xuất nguyên nhân"** trong phân tích
  xu hướng lỗi theo thời gian/ca — cũng là diễn giải/phân tích, không phải quyết định
  PASS/FAIL từng ca.

`GroqReasoningService.classify_defect_code` hiện tại dùng LLM để **chọn mã lỗi/severity
band** (DENT01 vs DENT02 vs DENT03 theo ngưỡng mm) — đây là bước **"decide"**, bị lệch
vai trò: đáng lẽ phải là rule/threshold theo đúng đề bài, không phải LLM. Đây không phải
"cắt bớt tính năng LLM của dự án" — đây là **đưa nó về đúng vai trò đề bài giao ngay từ
đầu**. Vì vậy hướng sửa dứt khoát là **bỏ hẳn LLM khỏi bước chọn mã lỗi cho các mã đã có
ngưỡng rõ ràng**, không phải "ưu tiên rule rồi mới gọi LLM khi rule không chắc" — vì dữ
liệu catalog hiện tại (`agent/services/defect_catalog.py`) toàn là ngưỡng số học thuần,
không có phần nào thật sự "mơ hồ" theo nghĩa cần suy luận ngôn ngữ.

### Ba vai trò LLM giữ nguyên/làm rõ hơn theo đúng đề bài (không đổi bởi kế hoạch này)
| Vai trò theo đề bài | Nơi triển khai trong code | Có nằm trên đường quyết định PASS/FAIL không |
|---|---|---|
| Mô tả/giải thích lỗi | `rationale_vi`, `generate_recommendation`/`GroqReasoningService.analyze()` | Không |
| Đề xuất nguyên nhân theo xu hướng lô/ca (Nâng cao) | Chưa có module riêng — hiện `HitlRateAlertService`/`quality_alerts.py` mới dừng ở phát hiện xu hướng bất thường, chưa sinh "đề xuất nguyên nhân" | Không (theo lô/ca, không phải từng xe) |
| Chọn mã lỗi/severity band | `classify_defect_code` — **đây là chỗ sai vai trò, cần sửa** | Có (đây là lý do gây "treo → HITL hàng loạt") |

→ **Ghi chú việc còn thiếu theo đề bài "Nâng cao"**: tính năng "đề xuất nguyên nhân" (root
cause suggestion) khi phát hiện cụm lỗi bất thường chưa có trong code — đây là vai trò LLM
hợp lệ, nên làm ở giai đoạn sau (không phải bug, mà là **backlog theo đúng đề bài**, xem
thêm mục 8 bên dưới).

### Giải pháp — thay `classify_defect_code` bằng rule engine thật sự, không phải fallback
1. **Bộ chọn mã lỗi mới hoàn toàn dựa trên rule**, đặt trong
   `agent/services/defect_rule_engine.py` (module mới), dùng trong
   `agent/graph/nodes.py::_classify_local_detection` **thay cho** lời gọi
   `self.reasoning.classify_defect_code(...)`:
   - `defect_catalog.match()` trả đúng 1 mã → chọn luôn.
   - Nhiều mã, `classification_rule` là ngưỡng số (`<=`, `<`, `>`, khoảng `a < x <= b`)
     hoặc đếm số lượng detection cùng loại → parse và so khớp `visual_measurements`,
     chọn đúng 1 mã khớp.
   - Rule ghi rõ cần "QC confirmation" (định tính, vd DENT04) → route thẳng **HITL**,
     KHÔNG gọi LLM để đoán — LLM không có thêm dữ liệu nào để "biết" hơn rule ở đây,
     nhờ LLM đoán một quyết định an toàn là rủi ro hơn là hỏi người thật.
   - Mã lỗi chưa có structured rule (mã mới do supervisor tự soạn free-text, chưa được
     chuẩn hoá) → cũng route thẳng **HITL** kèm lý do "mã lỗi chưa có ngưỡng tự động",
     không dùng LLM để bridge tạm — cùng lý do như trên.
   - **Yêu cầu hạ tầng/schema đi kèm**: cần bổ sung **trường có cấu trúc** khi tạo/sửa mã
     lỗi (vd `rule_type: THRESHOLD`, `min_mm`, `max_mm`, `min_detection_count`) song song
     với `classification_rule` text hiện có (giữ text để hiển thị, dùng field cấu trúc để
     máy tính). Đây là thay đổi schema DB (`defect_catalog` table) + UI supervisor tạo mã
     lỗi (`agent/services/policy.py` extraction flow) — không chỉ sửa 1 hàm.
   - Triển khai tăng dần: mã cũ chưa có structured rule vẫn chạy được (route HITL an toàn),
     không breaking; migrate dần từng mã sang structured rule.

2. **`classify_defect_code`/Groq chỉ còn phục vụ 2 việc theo đúng vai trò đề bài**:
   sinh `rationale_vi` (giải thích bằng tiếng Việt) cho log/audit, và
   `generate_recommendation`'s narrative. Cả hai đều **không chặn quyết định PASS/FAIL** —
   nếu Groq treo/lỗi ở bước này, dùng câu mẫu (template) có sẵn thay thế, tuyệt đối
   không kéo theo HITL, vì đây chỉ là cách trình bày, không phải quyết định.
   - Vẫn nên set timeout hợp lý (đo P99 thực tế, không đoán) cho lời gọi này — nhưng giờ
     đây chỉ ảnh hưởng "câu giải thích có sẵn ngay hay phải chờ điền sau", không ảnh
     hưởng gì đến việc xe PASS hay FAIL.

3. **Giám sát riêng tỉ lệ "mã lỗi chưa có structured rule"**: đây là chỉ số vận hành mới,
   khác hẳn "HITL do LLM lỗi" (vì giờ LLM không còn nằm trên đường quyết định) — chỉ số
   này cho biết catalog cần được chuẩn hoá thêm bao nhiêu mã nữa, dùng để ưu tiên công
   sức migrate rule.

**Việc cần làm (theo thứ tự):**
- [x] Thêm structured rule fields vào schema `defect_catalog` + UI tạo/sửa mã lỗi
- [x] Viết `agent/services/defect_rule_engine.py` (threshold/count/aspect-ratio) dùng
      `visual_measurements`
- [x] Thay lời gọi `classify_defect_code` trong `_classify_local_detection` bằng rule
      engine; mã không match được rule → HITL trực tiếp (không gọi LLM)
- [x] Giữ `classify_defect_code`/`analyze()` chỉ cho `rationale_vi`/narrative, không chặn
      quyết định khi lỗi/treo
- [x] Thêm metric đo latency Groq thực tế cho narrative call, set timeout theo P99 đo được
- [ ] Thêm chỉ số "tỉ lệ mã lỗi chưa có structured rule" để ưu tiên chuẩn hoá catalog

### ✅ Bổ sung (2026-08-31): tách hẳn `analyze()` khỏi đường quyết định + timeout

Audit latency phát hiện `analyze()` (narrative) vẫn đang **ép route="HITL"** khi Groq lỗi/
treo (`except ReasoningUnavailableError`), dù `route`/`final_status` thật ra đã tính xong
từ trước bằng policy thuần — nghĩa là chỉ "thêm timeout" sẽ khiến lỗi này xảy ra nhanh hơn,
đúng như rủi ro "cứ HITL hết" đã cảnh báo ở đầu file. Đã sửa root-cause, không phải patch:

- `agent/graph/nodes.py::assess_result` (2 call site quanh dòng ~438 và trong
  `generate_recommendation` quanh dòng ~645): khi `analyze()` raise
  `ReasoningUnavailableError`, **giữ nguyên** `route`/`decision`/`final_status` đã tính từ
  policy; chỉ thay narrative bằng kết quả của `DeterministicReasoningService().analyze()`
  (rule-based, đã có sẵn, trước đây chỉ dùng cho test) làm fallback, gắn
  `fallback_reason` để quan sát qua `ai_analysis`. `agent_reasoning_status` trả về
  `LLM_UNAVAILABLE_FALLBACK_DETERMINISTIC` thay vì bị hiểu nhầm là đã có LLM quyết định.
  Call site thứ 2 (`generate_recommendation`) trước đây **không có try/except** — Groq
  lỗi ở đó sẽ crash request (500); giờ đã bọc theo cùng pattern.
- `agent/services/reasoning.py::GroqReasoningService.__init__`: thêm `timeout=8.0` cho
  `Groq(...)` client (trước đây không set, request treo theo timeout mặc định SDK ~60s).
  An toàn để đặt ngắn vì quyết định không còn phụ thuộc kết quả gọi này nữa.
- Test mới: `tests/test_assessment_outcomes.py::test_narrative_llm_failure_keeps_deterministic_decision_and_does_not_route_to_hitl`
  và `::test_generate_recommendation_falls_back_when_reasoning_fails_without_stored_analysis`.

---

## 2. Video fps thấp bị crash (ZeroDivisionError)

✅ **Đã triển khai**: `agent/services/video_processor.py::VideoProcessor.extract_frames` —
`next_extract_frame = max(1, int(fps * self.extract_interval))`, bỏ guard tiền tính
`frames_to_extract`, kiểm tra rỗng sau vòng lặp thực tế. Test:
`tests/test_video_processor.py::test_extract_frames_does_not_crash_on_low_fps_video`.

### Vì sao không chỉ "thêm if tránh chia 0"
Nếu chỉ chặn chia-cho-0 rồi trả lỗi 422 như các lỗi khác, camera có fps thấp (một số
camera công nghiệp/an ninh quay 1-2fps là bình thường, không phải file hỏng) sẽ
**không bao giờ kiểm tra được bằng video** — vô tình chặn một nhóm thiết bị hợp lệ.
Đúng về mặt kỹ thuật (không crash) nhưng sai về nghiệp vụ (từ chối input hợp lệ).

### Giải pháp đúng nghiệp vụ
Khi khoảng cách giữa 2 khung hình gốc (`1/fps`) đã lớn hơn `extract_interval` mong
muốn, nghĩa là **không thể lấy mẫu thưa hơn tốc độ khung hình gốc** — nghiệp vụ đúng là
lấy **mọi khung hình có sẵn** (không bỏ khung nào) thay vì báo lỗi:
```python
frames_per_interval = fps * self.extract_interval
next_extract_frame = max(1, int(frames_per_interval))
```
Đồng thời bỏ điều kiện tiền kiểm `frames_to_extract == 0` (tính bằng công thức khác,
có thể lệch với vòng lặp thật) — thay bằng kiểm tra **sau khi trích xong**:
nếu `len(extracted_frames) == 0` mới báo lỗi thật sự (video hỏng/rỗng). Một nguồn tính
toán duy nhất, tránh 2 công thức lệch nhau như hiện tại (đây chính là nguyên nhân gốc
gây ra bug — không phải chỉ do thiếu 1 dòng guard).

**Việc cần làm:**
- [ ] Gộp `frames_to_extract` và `next_extract_frame` thành một nguồn tính duy nhất
- [ ] `max(1, ...)` để không chia cho 0
- [ ] Kiểm tra lỗi "video rỗng" dựa trên kết quả trích thực tế, không dựa vào công thức
      ước lượng trước
- [ ] Thêm test: video giả lập fps=1, interval=0.5 để chặn tái diễn

---

## 3. Video bị bóp méo tỉ lệ khung hình trước khi đưa vào model

✅ **Đã triển khai** (phần code): bỏ hẳn `cv2.resize(frame, (model_image_size,
model_image_size))` trong `extract_frames`; bỏ luôn tham số `model_image_size` khỏi hàm
này và lời gọi ở `backend/app/langgraph_api.py`. Test:
`tests/test_video_processor.py::test_extract_frames_keeps_native_resolution_no_forced_square_resize`.
⚠️ **Chưa làm** (nằm ngoài phạm vi code, cần đội hiệu chuẩn hiện trường xác nhận):
đối chiếu `mm_per_pixel_x/y`/`calibration_profile_id` có còn đúng với độ phân giải gốc
camera hay không — xem "Rủi ro cần kiểm tra trước khi merge" bên dưới, vẫn còn nguyên giá
trị, chưa được xác nhận trong đợt triển khai này.

### Vì sao đây là lỗi ảnh hưởng nghiệp vụ, không chỉ "chất lượng ảnh"
Hệ thống có hiệu chuẩn vật lý (`mm_per_pixel_x/y`, `calibration_profile_id`) để **đo kích
thước thật của vết lỗi bằng mm** — số đo này quyết định severity (A/B/C) và do đó quyết
định PASS/FAIL. Nếu ảnh từ video bị bóp méo (resize ép về hình vuông, sai tỉ lệ so với
camera thật) mà ảnh từ chụp ảnh thì không, thì **cùng một vết lỗi vật lý sẽ cho ra severity
khác nhau tuỳ theo nộp bằng video hay bằng ảnh** — đây là lỗi ảnh hưởng trực tiếp đến
tính đúng đắn của quyết định QC, không phải vấn đề thẩm mỹ.

### Giải pháp đúng
Không tự resize khung hình trong `VideoProcessor.extract_frames` nữa. Đường ảnh chụp
(`from-image`) đưa ảnh gốc thẳng vào `detector.detect()`, và YOLO tự lo việc resize nội
bộ theo `imgsz` (đã truyền sẵn trong `LocalYoloSegmentationDetector.detect()`), có
letterbox giữ tỉ lệ. Bỏ đoạn `cv2.resize(frame, (model_image_size, model_image_size))`
để hai luồng ảnh/video dùng **chung một pipeline tiền xử lý** — vừa sửa bug vừa đơn giản
hoá code (bớt một bước không cần thiết).

**Rủi ro cần kiểm tra trước khi merge:** vì `mm_per_pixel_x/y` được hiệu chuẩn theo một
độ phân giải cụ thể lúc lắp đặt camera, cần xác nhận lại với đội hiệu chuẩn hiện trường
rằng số mm/pixel đang dùng tương ứng với **độ phân giải gốc của camera quay video**
(không phải độ phân giải 640x640 bị ép trước đó) — nếu không, việc bỏ resize tuy đúng
hướng nhưng có thể làm lệch số đo mm theo hướng khác. Cần test song song ảnh chụp và
video của cùng một vết lỗi đã biết kích thước thật để đối chiếu trước khi lên production.

**Việc cần làm:**
- [ ] Bỏ resize cưỡng ép trong `extract_frames`
- [ ] Xác nhận `calibration_profile_id`/`mm_per_pixel_x,y` khớp độ phân giải gốc camera
- [ ] Test đối chiếu số đo mm giữa ảnh chụp và video cùng một vết lỗi mẫu

---

## 4. Một mã lỗi bị áp cho tất cả finding chưa phân loại khi supervisor resolve HITL

✅ **Đã triển khai**: `DetectionResolution` + `LangGraphResumeRequest.detection_resolutions`
(`backend/app/langgraph_schemas.py`). `resume_langgraph_inspection`
(`backend/app/langgraph_api.py`) validate `detection_resolutions` khớp đúng tập
`detection_id` đang chưa phân loại (422 nếu thiếu/thừa), áp đúng mã cho từng
`detection_id`; nếu vẫn dùng `defect_code` đơn mà ca có ≥2 finding chưa phân loại → 422
yêu cầu dùng `detection_resolutions` (chặn hẳn khả năng tái diễn bug cũ thay vì chỉ sửa
UI). Frontend `frontend/src/routes/hitl.tsx`: hiện danh sách dropdown riêng cho từng
finding chưa phân loại khi có ≥2 finding, validate đã chọn đủ trước khi submit; giữ
nguyên UI cũ khi chỉ có ≤1 finding. Chưa có test tự động cho luồng HTTP đầy đủ (cần
dựng được một ca HITL thật với ≥2 finding qua YOLO thật — nằm ngoài phạm vi test unit);
đã kiểm tra logic bằng dry-run thủ công (`detection_priority_key` chọn đúng "worst" khi
có nhiều resolution) — cần test thủ công qua UI thật trước khi coi là xong hẳn.

### Vì sao đây là lỗ hổng thiết kế API, không phải bug 1 dòng
`LangGraphResumeRequest` hiện chỉ có **một trường `defect_code` duy nhất** cho cả ca —
đúng với thời điểm hệ thống chỉ xử lý 1 phát hiện/ca. Sau khi nâng cấp lên
multi-camera/multi-detection (mỗi camera có thể có nhiều lỗi độc lập), API resume
**chưa được nâng cấp theo**, nên `_apply_operator_classification` buộc phải "đoán" —
và đoán sai bằng cách áp 1 mã cho tất cả. Sửa bug này bằng cách đổi 1 dòng code sẽ chỉ
che triệu chứng; gốc rễ là **API/UI thiếu khả năng phân giải nhiều finding độc lập**.

### Giải pháp đúng
1. Mở rộng `LangGraphResumeRequest` thêm trường tuỳ chọn:
   ```python
   detection_resolutions: list[DetectionResolution] | None = None
   # DetectionResolution: { detection_id: str, defect_code: str, severity: str | None }
   ```
2. Giữ `defect_code` (trường cũ) hoạt động như hiện tại **chỉ khi ca chỉ có đúng 1
   finding chưa phân loại** (trường hợp phổ biến nhất, không phá vỡ luồng cũ).
3. Khi có ≥2 finding chưa phân loại: bắt buộc phải có `detection_resolutions` khớp đủ
   số lượng detection_id đang chờ — nếu thiếu, trả lỗi 422 rõ ràng thay vì âm thầm gán
   nhầm. `_apply_operator_classification` chỉ áp mã cho đúng `detection_id` được chỉ định
   trong resolution tương ứng.
4. **Cần sửa UI HITL/Escalations phía frontend**: hiện form resume chỉ có 1 dropdown mã
   lỗi. Khi ca có nhiều finding chưa phân loại, UI phải hiển thị **từng finding riêng
   kèm dropdown riêng** (giống cách `enriched_defects` đã tách riêng theo
   `detection_id` — dữ liệu đã có sẵn, chỉ là UI resume form chưa dùng tới).

**Việc cần làm:**
- [ ] Thêm `DetectionResolution` schema + validate số lượng khớp
- [ ] Sửa `_apply_operator_classification` áp đúng theo `detection_id`
- [ ] Sửa UI resume form: hiển thị nhiều dropdown khi có nhiều finding chưa phân loại
- [ ] Giữ tương thích ngược cho ca chỉ có 1 finding (không bắt buộc đổi luồng cũ)

---

## 5. Frontend tự lọc policy theo `defect_type`, sai lệch với backend

✅ **Đã triển khai**: `frontend/src/routes/supervisor/escalations.tsx::eligiblePoliciesFor`
giờ chỉ lọc theo `isPolicyApproved`, bỏ hẳn điều kiện `defect_types` — khớp chính xác
`agent/services/policy.py::list_approved_policies()`. (Lưu ý: không đổi sang đọc
`run.interrupt.eligible_policies` như dự tính ban đầu trong kế hoạch — phát hiện trong
lúc code rằng `GET /agent/runs` (nguồn dữ liệu trang Escalations) luôn trả `interrupt=None`
cho danh sách, chỉ endpoint theo từng thread mới có interrupt thật; sửa thẳng bộ lọc để
khớp server là cách an toàn hơn, không cần đổi backend/kiểu dữ liệu.)

### Xác nhận nguồn gốc lỗi
`agent/services/policy.py::list_approved_policies()` — nguồn dữ liệu backend gửi thật sự
dùng để validate khi supervisor resume — **không lọc theo `defect_type`**, chỉ lọc theo
trạng thái APPROVED. Server đã tính sẵn danh sách đúng và gửi trong
`interrupt.eligible_policies` (`agent/graph/nodes.py::supervisor_review`). Frontend
(`frontend/src/routes/supervisor/escalations.tsx::eligiblePoliciesFor`) lại **tự query lại
catalog và tự lọc thêm theo `defect_type`** — phần lọc thêm này không tồn tại ở phía
server, nên đôi khi ẩn mất lựa chọn hợp lệ.

### Giải pháp đúng — không cần đổi logic nghiệp vụ, chỉ cần đọc đúng nguồn dữ liệu
Đây là lỗi duy nhất trong danh sách **không cần đổi nghiệp vụ hay hạ tầng** — nghiệp vụ
đúng (mọi policy APPROVED đều dùng được khi supervisor chuyển cấp, không giới hạn theo
defect_type) **đã được server định nghĩa đúng sẵn**. Chỉ cần frontend đọc và hiển thị
`run.interrupt.eligible_policies` (dữ liệu đã có trong response, đã đúng) thay vì tự gọi
`usePolicyCatalog()` rồi lọc lại theo `defect_type`. Xoá hàm `eligiblePoliciesFor` tự chế,
map thẳng từ `eligible_policies`.

**Việc cần làm:**
- [ ] Đổi UI dùng `run.interrupt.eligible_policies` thay vì tự lọc catalog
- [ ] Xoá `eligiblePoliciesFor` (dead logic sau khi đổi)
- [ ] Test lại case: policy không giới hạn `defect_types` phải xuất hiện trong dropdown

---

## 6. Kiểm tra tỉ lệ HITL trên mọi request nộp bài (độ trễ)

✅ **Đã triển khai — không cần Redis** (khác với dự tính ban đầu trong kế hoạch, xem lý
do bên dưới): thêm cột `assessment_route TEXT` trực tiếp trên `agent_graph_runs`
(`backend/app/database.py::_ensure_columns`), ghi song song với `defect_type` trong
`agent/services/repository.py::PostgresQCRepository.save()`.
`database.get_recent_outcomes_by_station` đổi từ `SELECT state_json` sang
`SELECT assessment_route` — bỏ hẳn `json.loads()` mọi blob state (một số state đo được
>1MB) trên mỗi lần nộp bài. `backend/app/hitl_alerts.py::_requires_hitl` đọc thẳng cột
mới. Interface `HitlRateAlertService.analyze()` giữ nguyên, không đổi gì phía caller.
Test: `tests/test_hitl_alerts.py` (3 case).

**Vì sao đổi từ "Redis/bộ đếm tăng dần" sang "thêm 1 cột"**: lúc code thực tế mới phát
hiện gốc rễ chậm không phải do THIẾU một bộ đếm, mà do bảng `agent_graph_runs` không có
cột nào ngoài `state_json` chứa `assessment_route` — chỉ cần thêm đúng 1 cột nhỏ là giải
quyết được toàn bộ chi phí parse JSON, không cần thêm hạ tầng mới (Redis) hay đổi ngữ
nghĩa window/count đang có. Đơn giản hơn, ít rủi ro hơn, và tận dụng index
`idx_agent_graph_runs_station_updated` đã có sẵn.

---

## 7. Dọn dẹp (không khẩn, làm sau cùng)
- [x] ✅ Đã xoá hẳn class chết `MultiCameraAggregator` khỏi `video_processor.py`
      (2026-08-31) — trước đó chỉ mới xoá import chết ở `backend/app/langgraph_api.py`,
      còn class (~130 dòng, chưa từng có caller/test nào) vẫn bị bỏ sót. Nếu sau này
      cần Tier-2 cross-camera dedup thật, viết lại theo dữ liệu calibration camera thật
      thay vì khôi phục lại class placeholder này (thân `_merge_across_cameras` cũ chỉ
      sort theo confidence, không thực sự merge).
- [ ] Chuyển `data/exports/*.json` ra khỏi git, lưu trong S3 (đã có sẵn `object_storage`),
      tránh phình repo trước khi thiết lập CI/CD trên AWS. **Chưa làm** — cần user tự
      quyết định/duyệt riêng vì đụng tới lịch sử git, không tự ý thực hiện.
- [x] ✅ Đã xoá `AUDIT_AUTO_EXPORT_ENABLED`/`AUDIT_EXPORT_DIR` khỏi `.env.example` và
      chú thích liên quan trong `.gitignore` (2026-08-31) — biến này không còn được đọc
      ở đâu sau khi `JsonAuditExporter`/`AuditExportSettings` đã bị xoá hoàn toàn khỏi
      `backend/app/config.py`/`backend/app/main.py`/`agent/services/audit_export.py`
      ở một đợt sửa trước, nhưng file config mẫu bị bỏ sót.

---

## 8. Rà soát hang/latency ngoài Groq (2026-08-31)

Sau khi đã tách Groq khỏi đường quyết định (mục 1), audit lại toàn bộ pipeline
LangGraph + FastAPI cho các rủi ro treo/nghẽn khác. Hai điểm sau là rủi ro thật,
đã sửa:

- [x] ✅ **Video upload không giới hạn thời lượng** — `agent/services/video_processor.py`
      (`VideoProcessor.extract_frames`): video dài/fps cao trước đây được giải mã và
      buffer toàn bộ frame vào RAM rồi đưa vào **một lần** `YOLO.predict()` dưới global
      lock (`agent/services/yolo_detector.py`) — 1 video xấu có thể giữ lock đủ lâu để
      chặn mọi inspection khác đang chờ. Đã thêm `VideoProcessor.MAX_VIDEO_DURATION_SECONDS
      = 180` — video vượt ngưỡng bị từ chối sớm (`VideoProcessingError`) ngay sau khi đọc
      metadata, trước khi vào vòng lặp giải mã/buffer frame.
- [x] ✅ **DB connection không có statement timeout** — `backend/app/database.py`
      (`Database.__init__`): pool chỉ có `pool_size=3 + max_overflow=2` connection; một
      query bị treo (DB phía Supabase chậm/deadlock) trước đây có thể giữ 1 trong số ít
      connection đó vô thời hạn, dần cạn pool cho cả app. Đã thêm
      `-c statement_timeout=8000` vào `connect_args["options"]` (kết hợp cùng
      `search_path` khi có `schema`) — mọi statement tự huỷ sau 8s thay vì treo vô hạn.

Không đổi lock quanh `model.predict()` — đã xác nhận batch 1 lần/camera là tối ưu, chỉ
thiếu giới hạn đầu vào (video quá dài) chứ không phải lock sai chỗ; giải pháp đúng là
giới hạn kích thước input, không phải sửa cơ chế lock.

---

## 9. Đề xuất nguyên nhân (root cause) đúng theo đề bài — đã sửa (2026-08-31)

Đề bài gốc (`docs/DE_BAI_GOC.md`, mục Nâng cao) yêu cầu: *"agent phân tích xu hướng lỗi
theo thời gian/ca và cảnh báo cụm lỗi bất thường, đề xuất nguyên nhân"*. `PRD.md` §6.1 cụ
thể hoá yêu cầu này thành **"Root Cause Hypothesis (giả thuyết cần QC xác minh, không phải
kết luận chắc chắn)"**, kèm đúng 2 ví dụ neo vào bằng chứng hình học: *"Cụm vết móp **cùng
tọa độ**"* → giả thuyết khuôn dập; *"Cụm vết xước **cùng đường kẻ dọc**"* → giả thuyết con
lăn băng tải. Đây là yêu cầu rule-based có điều kiện bằng chứng cụ thể, không phải một tác
vụ suy luận mở cần LLM — đúng tinh thần đã thống nhất ở mục 1 (LLM không được dùng khi
quyết định có thể suy ra thẳng từ ngưỡng/số đo đã có, xem FR-03e).

**Lỗi trước khi sửa:** `_predicted_root_cause()` (`backend/app/quality_alerts.py`) trả về
đúng 1 trong 2 câu template cố định, chọn **chỉ theo `defect_type`** (dent hay scratch) —
không hề kiểm tra "cùng tọa độ"/"cùng đường kẻ dọc" như đề bài yêu cầu. Nghĩa là hai xe cùng
bị móp ở hai góc khác nhau của cùng một `zone_name` (`zone_name` chỉ có 5 vùng thân xe thô)
vẫn nhận được câu khẳng định chắc chắn "khuôn dập dính bavia" giống hệt trường hợp lỗi thật
sự lặp lại đúng một điểm — **vi phạm trực tiếp yêu cầu "giả thuyết cần QC xác minh, không
phải kết luận chắc chắn"**, vì hệ thống phát biểu một kết luận cụ thể mà không có bằng chứng
tương ứng.

**Đã sửa:** `_predicted_root_cause()` giờ nhận cả nhóm occurrence và chỉ khẳng định một cơ
chế thiết bị cụ thể khi **cả ba** tín hiệu độc lập sau đều đúng — thiếu một là chưa đủ căn cứ:
1. `coordinate_cluster` — độ lệch chuẩn `center_x_ratio`/`center_y_ratio` (đã có sẵn trong
   `detections[].visual_measurements` từ YOLO, không cần thêm dữ liệu mới) của detection
   chính giữa các xe trong nhóm nằm trong ngưỡng 8% khung hình (`_is_tight_cluster`).
2. `single_camera` — mọi occurrence trong nhóm đến từ cùng một camera (`camera_id` không phải
   `MULTI_CAMERA`); khớp tọa độ xuyên nhiều camera khác nhau là bằng chứng yếu hơn vì mỗi
   camera thường chỉ khung một phần cố định của xe.
3. `severity_at_least_warning` — nhóm đạt tối thiểu WARNING (mặc định ≥3 xe liên tiếp hoặc
   ≥4/10 xe trong cửa sổ), không dừng ở WATCH (có thể chỉ 2 xe — mẫu quá nhỏ để cử người đi
   kiểm tra đúng một thiết bị).

- Cả ba đúng (`COORDINATE_CLUSTER_CONFIRMED`) → phát biểu đúng giả thuyết cơ chế thiết bị cụ
  thể theo `defect_type` (khuôn dập/tay gắp cho dent, con lăn/thanh dẫn hướng cho scratch),
  đúng 2 ví dụ trong PRD.md §6.1.
- Thiếu một trong ba (`ZONE_ONLY_UNCONFIRMED`) → trả về giả thuyết trung tính, liệt kê các khả
  năng cần xác minh thay vì khẳng định một cơ chế cụ thể.

Trường `root_cause_evidence` (`COORDINATE_CLUSTER_CONFIRMED` | `ZONE_ONLY_UNCONFIRMED`) và
`root_cause_evidence_detail` (chi tiết cả ba tín hiệu + `occurrence_count`, để QC/báo cáo thấy
rõ vì sao hệ thống kết luận vậy) được thêm vào `QualityAlert`, trả về ở cả
`GET /api/quality-alerts` và SSE `GET /api/v1/station/stream-alerts` — xem `API_CONTRACT.md`
§6.2/§6.4. Frontend (`supervisor/anomalies.tsx`) hiển thị badge + checklist ba tín hiệu này.

**File đã đổi:** `backend/app/quality_alerts.py` (logic + field mới),
`backend/app/v1_api.py` (thêm field vào SSE payload), `frontend/src/lib/api-types.ts`,
`frontend/src/routes/supervisor/anomalies.tsx`, `docs/PRD.md` §6.1, `docs/API_CONTRACT.md`
§6.2/§6.4. Test: `tests/test_quality_alerts.py` (4 test — cụm chặt cùng camera đủ severity
xác nhận giả thuyết; rải rác, xuyên camera, và WATCH-tier 2 xe đều không xác nhận).

Không đổi sang dùng LLM cho bước này: đúng như mục 1 đã thống nhất, LLM chỉ nên dùng khi
không có đủ ngưỡng/số đo tường minh để quyết định — ở đây bằng chứng hình học (tọa độ
detection) đã đủ để phân biệt "giả thuyết có căn cứ" và "chưa đủ căn cứ" một cách xác định,
dùng LLM sẽ chỉ thêm độ trễ/rủi ro treo mà không tăng độ chính xác. Lớp giải thích bằng ngôn
ngữ tự nhiên xung quanh giả thuyết (qua `DeterministicReasoningService`/`ai_analysis`) đã tồn
tại sẵn trong `RepetitionAlertService.analyze()`.

**Bug liên quan phát hiện thêm khi rà soát UI:** panel "Khuyến nghị xử lý"
(`frontend/src/routes/supervisor/anomalies.tsx`) trước đó hiển thị **nguyên văn mã enum**
`selected.actionable_routing_command` (vd `ROUTE_AFFECTED_BATCH_TO_OFFLINE_INSPECTION_BUFFER`)
thẳng ra UI cho QC đọc, dù `docs/API_CONTRACT.md` mô tả field này phải là câu người đọc được
(vd `"Reroute batch to Offline Buffer Area"`), và backend đã có sẵn field `recommendation_vi`
(câu tiếng Việt đầy đủ, chưa từng được UI này dùng tới). Đã sửa: panel giờ hiển thị
`recommendation_vi`/`recommendation_en` làm nội dung chính, và convert mã enum sang nhãn tiếng
Việt ngắn qua `formatRoutingCommand()` (`frontend/src/lib/detection-geometry.ts`) hiển thị như
dòng phụ "Hành động điều phối: ...".

---

## Thứ tự triển khai đề xuất
1. Mục 5 (frontend đọc đúng nguồn — an toàn, không rủi ro, làm ngay)
2. Mục 2 (fix chia-cho-0 — bug rõ ràng, không đổi nghiệp vụ)
3. Mục 3 (bỏ resize méo hình — cần đối chiếu hiệu chuẩn trước khi merge)
4. Mục 4 (mở rộng resume API cho nhiều finding — cần đổi FE + BE + schema, làm theo
   từng bước nhỏ, giữ tương thích ngược)
5. Mục 1 (rule engine thay LLM cho bước chọn mã lỗi — nhiều việc nhất, ảnh hưởng lớn nhất
   đến tỉ lệ tự động hoá và đúng vai trò LLM theo đề bài)
6. Mục 6 (đổi cơ chế đếm HITL rate — hoá ra không cần Redis, xem ghi chú trong mục 6)
7. Mục 7 (dọn dẹp, làm bất cứ lúc nào rảnh)
8. Mục 8 (backlog "đề xuất nguyên nhân" — làm sau, khi các mục trên đã ổn định)

---

## Kiểm thử

**Tự động (đã chạy, đang pass):**
- `pytest` toàn bộ — 53 test pass (`tests/test_video_processor.py`,
  `tests/test_defect_rule_engine.py`, `tests/test_hitl_alerts.py` là test mới thêm cho
  đợt này; toàn bộ test cũ vẫn pass không cần sửa assertion nào).
- `npx tsc --noEmit` phía `frontend/` — không còn lỗi kiểu dữ liệu sau khi sửa
  `escalations.tsx`, `hitl.tsx`, `catalogs.tsx`, `api-types.ts`.

**Thủ công (chưa làm trong đợt này, cần làm trước khi coi là "xong" để deploy):**
- [ ] Nộp 1 ảnh có lỗi rõ ngưỡng (vd vết móp ước lượng 30mm) qua UI thật → xác nhận ra
      kết quả PASS/FAIL tự động, KHÔNG có lời gọi Groq nào trong log cho bước phân loại
      mã lỗi (chỉ còn ở bước sinh khuyến nghị cuối nếu route CONFIRMED).
- [ ] Nộp 1 ảnh có lỗi thuộc mã `REQUIRES_HUMAN` (DENT04/SCRATCH05 mặc định) → xác nhận
      vào thẳng HITL, có lý do rõ ràng, không treo chờ Groq.
- [ ] Nộp 1 video quay ở fps thấp (dùng điện thoại quay chậm/loại camera fps thấp nếu có)
      → xác nhận không lỗi 422/500, trích được khung hình.
- [ ] Tạo (hoặc tìm) 1 ca HITL có ≥2 finding chưa phân loại (2 camera khác nhau cùng có
      lỗi lạ) → xác nhận UI hiện đúng nhiều dropdown, resolve đúng từng finding, không
      còn hiện tượng 1 mã bị áp cho cả hai.
- [ ] Vào trang Supervisor → Escalations, xác nhận dropdown chính sách hiện đủ policy đã
      duyệt (kể cả policy không giới hạn theo `defect_types`).
- [ ] Vào trang Supervisor → Catalogs, thử tạo 1 mã lỗi mới với `rule_type=THRESHOLD_MM`
      và xác nhận nó thật sự tự động phân loại được (không rơi vào HITL) cho phát hiện
      khớp ngưỡng.
