# Visual QC Agent Flow

Hệ thống chạy upload-only với model segmentation local `data/best.pt`.
Frontend không cung cấp class, confidence, bbox hoặc mask; toàn bộ detection đến
từ model và được LangGraph điều phối. **Phân loại mã lỗi** (bước "classify") chạy
bằng rule engine deterministic (`agent/services/defect_rule_engine.py`, ngưỡng
mm/số lượng — KHÔNG dùng LLM). **Quyết định PASS/FAIL/HITL** (bước "decide") do
`assess_result` tính hoàn toàn từ policy + ngưỡng confidence (`CONFIRMED_THRESHOLD`,
mặc định `0.85`) — một finding dưới ngưỡng này, dù đã khớp danh mục, vẫn bị coi
là mơ hồ và route sang HITL trừ khi đã có finding khác đủ tin cậy chốt `FAIL`
trước. Groq LLM (hoặc `DeterministicReasoningService` khi chạy rule-based) chỉ
sinh **narrative giải thích sau khi quyết định đã chốt** — không được tự đổi
`action_code`/`final_status`/`allow_test_drive` (3 lớp guard trong
`GroqReasoningService.analyze`, `agent/services/reasoning.py`).

```mermaid
flowchart TD
    START --> prepare_input
    prepare_input --> detect_defect
    detect_defect --> assess_result
    assess_result -->|PASS| save_result
    assess_result -->|CONFIRMED| generate_recommendation
    assess_result -->|HITL| human_review
    human_review -->|APPROVE/REJECT| generate_recommendation
    human_review -->|OVERRIDE| supervisor_review
    supervisor_review --> generate_recommendation
    generate_recommendation --> save_result
    save_result --> END
```

Node `verify_defect`/route `VERIFY` (`ModelVerifier`, second-pass re-inference)
từng được định nghĩa trong graph nhưng `assess_result` không bao giờ trả về
route đó — chưa từng chạm tới được kể từ khi được thêm vào. Đã xoá khỏi runtime
ngày 2026-09-04; yêu cầu "ngưỡng tin cậy để tự động chuyển người khi mơ hồ"
(`docs/DE_BAI_GOC.md`) nay được đáp ứng trực tiếp bằng `CONFIRMED_THRESHOLD`
trong `assess_result`, không cần một node re-inference riêng.

Không còn node xác minh thị giác bằng Multimodal LLM (`multimodal_verify`) trong
runtime — bước này đã bị bỏ khỏi baseline (xem `docs/PRD.md` §7.3, v1.4).
YOLO segmentation + Geometry Processor deterministic là evidence duy nhất trước
`assess_result`.

## HITL hai cấp (Inspector → Supervisor)

- **`human_review`** (mọi role đã đăng nhập có thể mở case được phân công) chỉ
  chấp nhận 3 hành động: `APPROVE` (xác nhận lỗi AI gắn cờ là thật →
  `final_status = FAIL`), `REJECT` (bác bỏ lỗi, không có defect thật →
  `final_status = PASS` ngay, không có bước tái kiểm tra riêng), `OVERRIDE`
  (đề xuất một hành động tùy biến, bắt buộc chuyển cấp).
- **`supervisor_review`** chỉ chạy khi `human_review` chọn `OVERRIDE`, và chỉ
  role `QC_SUPERVISOR` mới resume được (`backend/app/langgraph_api.py` trả 403
  nếu sai role). Chỉ nhận `APPROVE` (giữ đề xuất của Inspector → `FAIL`) hoặc
  `REJECT` (bỏ đề xuất, quay lại quyết định QC Rules chuẩn theo `defect_type`).
- `final_status` chỉ có hai giá trị: `PASS` hoặc `FAIL`. Không còn
  `HOLD_FOR_QC`/`HOLD_FOR_REWORK`/`HUMAN_OVERRIDE_APPLIED`/trạng thái tái kiểm
  tra (`REINSPECT`) riêng — mọi FAIL, dù tự động hay qua HITL, đều là một giá
  trị duy nhất và luôn đi thẳng đến Rework.

## Runtime services

| Thành phần | Implementation hiện tại |
| --- | --- |
| Detector | `LocalYoloSegmentationDetector(data/best.pt)` (luôn phải được inject thật khi build graph — không còn detector giả trong runtime path) |
| Rule engine (classify) | `classify_by_rule` (`agent/services/defect_rule_engine.py`) — thuần ngưỡng mm/số lượng, không LLM |
| Reasoning (explain) | Groq LLM sinh narrative giải thích sau khi policy đã chốt quyết định; backend validate schema, catalog và policy, không cho Groq tự đổi quyết định. `DeterministicReasoningService` dùng cho test/rule-based mode hoặc khi Groq lỗi (fallback narrative, không đổi route) |
| Checkpointer | `InMemorySaver` cho pause/resume HITL |
| Audit | PostgreSQL/Supabase table `agent_graph_runs` |
| Evidence | S3/MinIO object storage (`data/uploads` chỉ là scratch cục bộ trước khi upload — xem `docs/API_CONTRACT.md` §4) |

## Luồng upload

1. QC tải JPEG/PNG lên `POST /inspections/from-image`.
2. Backend kiểm tra content type, dung lượng và xác thực ảnh bằng Pillow.
3. Ảnh được hash SHA-256 và đưa vào `QCState`, đồng thời lưu vào S3/MinIO.
4. `best.pt` trả class, confidence, bbox và segmentation polygon.
5. `assess_result` route theo `CONFIRMED_THRESHOLD`: finding confident (đã khớp
   danh mục và confidence ≥ ngưỡng) đi qua policy để quyết `PASS`/`FAIL` ngay;
   finding mơ hồ (chưa khớp hoặc dưới ngưỡng) route sang `human_review`, trừ khi
   một finding confident khác đã chốt `FAIL` trước đó (worst-wins, không chờ).
6. Kết quả không rõ dừng tại `human_review` (và có thể `supervisor_review`) bằng `interrupt()`.
7. Kết quả cuối được lưu vào `agent_graph_runs`; UI hiển thị node trace, ảnh
   evidence, mã lỗi, số đo pilot và hành động cuối.
8. Case bị `interrupt()` xuất hiện trong Hàng đợi QC dưới dạng thẻ kiểm duyệt có
   ảnh và lý do cần người xử lý. Sau `Command(resume=...)`, bản ghi hoàn tất được
   chuyển sang Lịch sử.

## Ranh giới test double

Runtime luôn dùng detector/repository thật khi build graph
(`agent/graph/builder.py` không còn fallback mock). Test double (nếu có) chỉ
tồn tại trong `tests/` để kiểm tra các nhánh LangGraph nhanh và deterministic;
chúng không cung cấp dữ liệu cho giao diện production.

## Quality trend alert

Agent đọc bản ghi mới nhất của mỗi xe trong 24 giờ và nhóm theo
`defect_type + zone_name + camera_id`:

- từ 3 xe: `WARNING`, yêu cầu QC kiểm tra công đoạn phía trước;
- từ 5 xe: `CRITICAL`;
- UI hiển thị mã lỗi liên quan và tối đa bốn ảnh không trùng của các lần phát hiện;
- cảnh báo chỉ giữ tín hiệu chính, hành động ngay, kết luận Agent và điều kiện đóng;
- báo cáo Word tải tại `GET /api/quality-alerts/report.docx`.
