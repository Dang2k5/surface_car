# Dataset Documentation — Visual QC Agent (YOLO Segmentation)

Tài liệu này mô tả dataset dùng để huấn luyện/đánh giá YOLO Segmentation cho
hai lớp taxonomy MVP: `scratch`, `dent` (xem `PRD.md` §7.1). Domain mục tiêu
là **vehicle production / final visual QC** (kiểm tra ngoại quan xe mới trước
xuất xưởng tại trạm FNS) — không dùng dữ liệu tai nạn nghiêm trọng hoặc
domain không liên quan (xe cũ đã va chạm nặng, ảnh sửa chữa hậu tai nạn), vì
không phù hợp với bối cảnh kiểm tra cosmetic tại chốt hoàn thiện dây chuyền.

## Trạng thái hiện tại: TODO

Repository hiện chưa cung cấp đủ thông tin để điền đầy đủ các mục dưới đây.
Không bịa số liệu; các mục sau cần Team 235 xác nhận và cập nhật trực tiếp
vào file này khi có dữ liệu chính thức.

| Mục | Trạng thái |
| --- | --- |
| Dataset source (public / simulated / nội bộ) | TODO — chưa xác định |
| License | TODO — chưa xác định |
| Số lượng ảnh (tổng) | TODO — chưa xác định |
| Train / Validation / Test split | TODO — chưa xác định |
| Classes | `scratch`, `dent` (khớp `PRD.md` §7.1 taxonomy MVP) |
| Segmentation annotation format | TODO — chưa xác định (ví dụ: COCO-seg, YOLO-seg polygon) |
| Image resolutions | TODO — chưa xác định |
| Cleaning / dedup policy | TODO — chưa xác định |
| Augmentation policy | TODO — chưa xác định |
| Domain | vehicle production / final visual QC (FNS station) |
| Annotation policy / labeling guideline | TODO — chưa xác định |
| Excluded domain | Không dùng ảnh tai nạn nghiêm trọng hoặc xe đã qua sửa chữa lớn, vì lệch domain kiểm tra ngoại quan xe mới |

## Ràng buộc khi bổ sung dataset

- Chỉ thu thập/gắn nhãn ảnh phù hợp domain kiểm tra ngoại quan trước xuất
  xưởng (FNS station hoặc tương đương).
- Giữ đúng hai lớp taxonomy MVP `scratch`/`dent`; không tự thêm `paint_defect`
  vào tập nhãn production khi chưa được phê duyệt mở rộng taxonomy
  (`PRD.md` §11 — Future Extension).
- Annotation phải là segmentation mask/polygon (không chỉ bounding box) để
  phục vụ Geometry Extraction (`PRD.md` §7.2).
- License và nguồn dữ liệu phải được ghi rõ trước khi dùng cho huấn luyện
  hoặc công bố kết quả.
