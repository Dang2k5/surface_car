# Demo workflow Agent theo policy

Tài liệu này mô tả hành vi đang chạy của baseline MVP tại trạm FNS. Mục tiêu
là trình bày rõ Agent nhận gì từ Computer Vision, phân tích qua từng checkpoint,
dừng ở đâu khi lỗi, chọn phương pháp nào và ghi gì vào SQLite.

> Cảnh báo phạm vi: mọi reference `DEMO-QC-*`, tolerance, GD&T, material,
> severity và phương pháp trong bản này là policy nội bộ phục vụ mô phỏng.
> Chúng chưa phải tiêu chuẩn OEM/nhà máy. Trước production phải thay bằng
> specification và work instruction được QC Engineering phê duyệt, có version.

## 1. Agent đóng vai trò gì?

Agent hiện tại là workflow LangGraph deterministic. Nó có bốn trách nhiệm:

1. Điều phối đúng thứ tự các checkpoint.
2. Chỉ cho phép bước sau chạy khi bước trước hoàn thành.
3. Tra policy demo để chọn một `action_code` và danh sách bước thực hiện cụ thể.
4. Lưu trace đầy đủ để QC xem lại và audit.

Baseline không gọi mô hình ngôn ngữ bên ngoài. Lý do, action, route và quyền test
drive đều được sinh từ state và policy có thể kiểm chứng.

## 2. Workflow sáu checkpoint

```text
Ảnh local / payload CV mock
          |
          v
01 detect -------- lỗi --> STOPPED_RETRY_REQUIRED
          |
02 validate ------ lỗi --> STOPPED_RETRY_REQUIRED
          |
03 classify ------ lỗi --> STOPPED_RETRY_REQUIRED
          |
04 policy_evaluate lỗi --> STOPPED_RETRY_REQUIRED
          |
05 route
          |
06 HITL: NOT_REQUIRED hoặc WAITING
```

| Checkpoint | Agent kiểm tra/thực hiện | Output chính |
|---|---|---|
| `detect` | Tiếp nhận detection đã persist từ payload YOLO-shaped | defect type, confidence, bbox, camera/model |
| `validate` | Kiểm tra bbox, miền confidence và liên kết inspection | payload hợp lệ hoặc error code |
| `classify` | Ánh xạ defect vào catalog domain mock | panel, material, GD&T, tolerance, measurement, severity |
| `policy_evaluate` | So khớp safety gate và policy | recommendation, action code, refs, method steps |
| `route` | Khóa route và quyền test drive | khu vực đích, allow/block test drive |
| `hitl` | Xác định có cần người duyệt định danh hay không | `NOT_REQUIRED` hoặc `WAITING` |

Mỗi step ghi `name`, `status`, `detail`, `policy_refs`, `error_code` và
`retryable`. Các step phía sau không được tạo nếu workflow đã dừng.

## 3. Dừng và chạy lại

Khi một checkpoint lỗi, workflow trả:

```json
{
  "status": "STOPPED_RETRY_REQUIRED",
  "decision": null,
  "steps": [
    {
      "name": "classify",
      "status": "STOPPED",
      "error_code": "SIMULATED_CLASSIFY_FAILURE",
      "retryable": true,
      "policy_refs": ["DEMO-QC-RECOVERY-001"]
    }
  ]
}
```

Không có decision và route sau điểm lỗi. Trên màn hình **Mô phỏng CV**, chọn
checkpoint lỗi để trình diễn, sau đó bấm **Chạy lại mô phỏng sạch**. Payload
thiếu bbox là lỗi dữ liệu thật trong baseline và dùng mã
`CV_PAYLOAD_VALIDATION_FAILED`.

## 4. Catalog phương pháp hiện tại

| Điều kiện demo | `action_code` | Phương pháp/route | Test drive |
|---|---|---|---|
| Không có defect | `RELEASE_TO_NEXT_QUALITY_GATE` | Ghi kết quả, xác nhận VIN/check bắt buộc, chuyển quality gate tiếp theo | Cho phép theo policy demo |
| Lỗi bề mặt nhỏ, confidence đủ và trong tolerance | `SURFACE_POLISH_AND_REINSPECT` | Bảo vệ trim, làm sạch, polish theo WI được duyệt, kiểm tra lại dưới ánh sáng kiểm soát, QC xác nhận | Chỉ release sau QC xác nhận |
| Vượt tolerance, rank P/S/A hoặc hot-stamped steel | `ISOLATE_FOR_BODY_REPAIR_ASSESSMENT` | HOLD, cấm test drive, không cold-work tự phát, xác nhận repairability, chuyển Body Rework Assessment | Cấm |
| Lỗi sơn/Class-A surface | `ISOLATE_FOR_PAINT_REPAIR_ASSESSMENT` | HOLD, bảo vệ khỏi contamination, đánh giá sửa sơn theo WI, kiểm tra appearance/measurement lại | Cấm |
| Classification confidence `< 0.80` | `MANUAL_VISUAL_REINSPECTION` | Giữ tại QC bay, kiểm tra ánh sáng kiểm soát, xác nhận panel/material/measurement, reviewer định danh quyết định | Cấm khi chờ |
| Có detection nhưng thiếu classification | `RETRY_CLASSIFICATION_PIPELINE` | Giữ xe tại quality gate, kiểm tra payload/master data, retry, escalation nếu lặp lại | Cấm |

Tên Plan A/Plan B không còn là output nghiệp vụ mới. Enum cũ chỉ được giữ trong
schema để đọc các record SQLite legacy đã tạo trước khi migration.

## 5. Policy references

| Reference demo | Ý nghĩa |
|---|---|
| `DEMO-QC-DATA-001` | Tính đầy đủ và hợp lệ của dữ liệu |
| `DEMO-QC-CLASSIFY-001` | Catalog phân loại domain mock |
| `DEMO-QC-COSMETIC-001` | Điều kiện vào sửa bề mặt có kiểm soát |
| `DEMO-QC-BODY-001` | Điều kiện đánh giá sửa thân vỏ |
| `DEMO-QC-PAINT-001` | Điều kiện đánh giá sửa sơn |
| `DEMO-QC-HOLD-001` | HOLD và khóa test drive |
| `DEMO-QC-HITL-001` | Yêu cầu người duyệt định danh |
| `DEMO-QC-RELEASE-001` | Điều kiện release demo |
| `DEMO-QC-RECOVERY-001` | Dừng, retry và escalation |

## 6. Dữ liệu SQLite

Database mặc định là `data/visual_qc.db`.

```text
inspections 1---N defects
     |             |
     |             +---N classifications
     +---N decisions
     |       |
     |       +---N hitl_reviews
     +---N workflow_runs
```

| Bảng | Nội dung chính |
|---|---|
| `inspections` | VIN, model, station, trạng thái và thời điểm tạo |
| `defects` | Output YOLO-shaped: class/type, confidence, bbox, kích thước ảnh, camera/model, severity mock |
| `classifications` | panel, material, GD&T group, tolerance, measurement, severity, confidence và source |
| `decisions` | recommendation, `action_code`, route, reason codes, `policy_refs`, `method_steps`, explanation và test-drive gate |
| `hitl_reviews` | reviewer, confirm/override/reject, recommendation gốc/cuối, lý do và timestamp |
| `workflow_runs` | status và toàn bộ trace JSON của một lần chạy |

Các trường danh sách trong SQLite đang được serialize dưới dạng JSON text. Đây là
giải pháp baseline; khi chuyển PostgreSQL có thể chuẩn hóa thành các bảng policy,
policy version, action catalog và workflow event riêng.

## 7. Kịch bản demo đề xuất

1. Mở **Mô phỏng CV**, chọn ảnh scratch confidence cao và chạy bình thường.
2. Chỉ bbox/payload CV, sáu checkpoint, policy refs và method steps.
3. Chọn ảnh dent để chỉ safety gates, HOLD, body assessment và test-drive block.
4. Chọn ảnh confidence thấp để chỉ `MANUAL_VISUAL_REINSPECTION` và HITL queue.
5. Chọn **Lỗi tại classify**, chạy lại và chỉ rằng trace dừng ở bước 03, decision
   là `null`, route không chạy.
6. Bấm **Chạy lại mô phỏng sạch** để hoàn thành cùng case.
7. Mở trace LangGraph để đối chiếu từng node, state update và quyết định đã lưu.

## 8. API demo nhanh

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/simulations/cases

$body = @{ fail_at_step = "classify" } | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/simulations/train-21-scratch/run" `
  -ContentType "application/json" `
  -Body $body
```

Chạy bình thường bằng body `{}` hoặc bỏ `fail_at_step`.

## 9. Dữ liệu cần từ QC Engineering trước production

- Part/panel/material master theo model và VIN.
- GD&T zone, tolerance, phương pháp đo và uncertainty.
- Severity rank PSLAWBCD có định nghĩa và escalation được phê duyệt.
- Catalog defect-to-disposition theo từng part/material/zone.
- Repair work instruction có mã tài liệu, revision, hiệu lực và giới hạn áp dụng.
- HOLD/release/test-drive authorization matrix.
- Quy tắc conflict, retry limit, escalation SLA và quyền override.

Khi có các nguồn trên, Agent chỉ được chọn action từ catalog đã version hóa;
không được để thành phần sinh nội dung tự sáng tạo phương pháp sửa chữa.
