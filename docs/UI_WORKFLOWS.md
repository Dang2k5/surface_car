# Visual QC Workstation — UI workflows

Tài liệu này mô tả hành vi giao diện của baseline MVP tại trạm FNS. UI tập trung
vào thông tin giúp QC quyết định; dữ liệu kỹ thuật đầy đủ vẫn được giữ trong
LangGraph state và audit trace.

## 1. Điều hướng chính

| Màn hình | Mục đích |
|---|---|
| Tổng quan | Giới thiệu hệ thống, trạng thái ca và các kết quả mới nhất |
| Kiểm tra bằng Agent | Upload ảnh/video camera chính, theo dõi workflow và xem quyết định |
| Hàng đợi QC | Xử lý các LangGraph thread đang dừng tại HITL |
| Sổ mã lỗi QC | Quản lý ánh xạ label CV sang mã lỗi nghiệp vụ |
| Cảnh báo lặp lỗi | Theo dõi cụm lỗi lặp lại và kiểm tra khâu trước |
| Lịch sử | Tra cứu inspection đã hoàn tất và mở lại state đầy đủ |

Baseline chỉ sử dụng `vehicle_id`, `vehicle_model`, `camera_id` và `zone_name` làm
ngữ cảnh upload. `vin_code`, `panel` và `material` đã được loại khỏi UI và API.

## 2. Kiểm tra bằng Agent

```text
Chọn ảnh/video
  → frontend cắt frame nếu input là video
  → POST /inspections/from-image
  → best.pt detect/segment
  → LangGraph chạy từng node
  → quyết định tự động hoặc interrupt HITL
```

Khi workflow đang chạy, khu vực Kết quả & Điều phối hiển thị live node trace.
Khi hoàn tất, kết quả vận hành thay thế trace và chỉ giữ các thông tin chính:
lỗi, mã lỗi, confidence, kích thước/vị trí, policy áp dụng và hành động.

## 3. Hàng đợi QC

Chỉ hiển thị run có trạng thái `INTERRUPTED`. Mỗi thẻ gồm:

- ảnh evidence;
- mã xe và thread ID;
- loại lỗi và mã lỗi; nếu là lỗi mới, UI ghi rõ cần QC phân loại;
- confidence, kích thước ước tính, vị trí và camera;
- lý do Agent chuyển checkpoint;
- trạng thái và CTA **Mở kiểm duyệt**.

QC mở case, nhập kết luận và resume graph. Backend dùng
`Command(resume=...)`; case hoàn tất sẽ rời hàng đợi và xuất hiện trong Lịch sử.

## 4. Cảnh báo lặp lỗi

Agent phân tích cửa sổ inspection gần nhất và nhóm theo loại lỗi, vùng quan sát và
camera. UI trình bày theo thứ tự:

1. Tín hiệu: loại lỗi, số lần lặp, số xe, camera và lần phát hiện gần nhất.
2. Bằng chứng trực quan: mã lỗi liên quan và tối đa bốn ảnh không trùng.
3. Hành động ngay: tối đa ba bước kiểm tra khâu trước.
4. Kết luận Agent: nguồn nghi ngờ và bộ phận chịu trách nhiệm.
5. Điều kiện đóng: QC ghi nhận kiểm tra và xác nhận lỗi không còn lặp lại.

UI không hiển thị routing command thô, trigger code nội bộ, bảng phân bố điều
phối hoặc các đoạn reasoning trùng nhau. Báo cáo Word vẫn tải qua
`GET /api/quality-alerts/report.docx`.

## 5. Lịch sử

Mỗi inspection đã hoàn tất được hiển thị thành một thẻ có:

- thumbnail evidence;
- mã xe, inspection ID và thread ID;
- loại lỗi và mã lỗi Agent phân loại;
- confidence và camera;
- kích thước pilot và vị trí tương đối;
- hành động cuối, trạng thái và thời điểm QC xác nhận nếu có.

Nhấn thẻ để mở lại kết quả đầy đủ. Nút **Xóa lịch sử** gọi
`DELETE /agent/runs`; thao tác này xóa trace/state nhưng không xóa ảnh upload.

## 6. Responsive và trạng thái rỗng

- Desktop ưu tiên ảnh cạnh dữ liệu để QC quét nhanh nhiều case.
- Tablet chuyển facts thành hai cột.
- Mobile chuyển thẻ thành một cột, ảnh tỷ lệ 16:9 và giữ nguyên CTA chính.
- Khi thiếu ảnh, UI hiển thị thông báo rõ ràng; không dùng ảnh mock thay thế.
- Các giá trị vùng bắt đầu bằng `unknown` không được dùng làm tiêu đề cảnh báo.

## 7. Tiêu chí nghiệm thu UI

- QC nhận ra lỗi, xe ảnh hưởng và hành động tiếp theo mà không mở audit thô.
- Hàng đợi giải thích rõ lý do con người phải can thiệp.
- Cảnh báo có đủ mã lỗi và ảnh để đối chiếu hiện tượng lặp.
- Lịch sử cho phép truy vết từ quyết định về evidence và LangGraph thread.
- Giao diện Việt–Anh không làm thay đổi dữ liệu hoặc trạng thái workflow.
