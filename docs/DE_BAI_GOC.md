# ĐỀ BÀI GỐC — VISUAL QC AGENT

> **Mục đích của file này:** lưu nguyên văn nội dung nhìn thấy trong 2 ảnh đề bài đã được cung cấp, để làm nguồn yêu cầu gốc khi rà soát và cập nhật tài liệu dự án.  
> Chỉ chuẩn hóa xuống dòng/Markdown để dễ đọc; không diễn giải, không bổ sung yêu cầu mới.

---

## Bối cảnh đề tài MFG-04

**Khối Sản xuất X – Hệ thống sản xuất**  
(Xe X, Doanh nghiệp vật liệu X, Doanh nghiệp năng lượng X)

**MFG-04**

**AI Agent Kiểm Tra Chất Lượng Bề Mặt Bằng Computer Vision (Visual QC Agent)**

📍 **Thực trạng:** Kiểm tra lỗi bề mặt thân vỏ xe/tấm pin (xước, móp, lỗi sơn) chủ yếu bằng mắt thường, phụ thuộc kinh nghiệm và mệt mỏi của công nhân, dễ bỏ sót.

🎯 **Vấn đề:** Cần AI Agent nhận ảnh sản phẩm từ trạm kiểm tra, phát hiện & phân loại lỗi, khoanh vùng, quyết định PASS/FAIL/cần người kiểm, ghi nhận và thống kê lỗi theo lô.

🔒 **Ràng buộc:** Sản phẩm nghi ngờ hoặc lỗi nghiêm trọng phải chuyển HITL (QC duyệt trước khi loại bỏ); an toàn khi tích hợp trạm; bảo mật hình ảnh sản phẩm (bí mật thiết kế); cân bằng độ chính xác (không để lọt lỗi lẫn không loại nhầm hàng tốt); độ trễ đủ nhanh cho nhịp dây chuyền.

---

## Công nghệ và yêu cầu triển khai

• Computer Vision (YOLOv8/Detectron2 phát hiện lỗi) + LLM đa phương thức (mô tả/giải thích lỗi)  
• LangGraph điều phối (detect → classify → decide → HITL)  
• dataset ảnh lỗi mô phỏng/công khai  
• backend FastAPI + lưu ảnh (S3/MinIO)  
• frontend React hiển thị bounding box  
• deploy cloud có GPU/CPU inference.

### Cơ bản

• Web deploy, đăng nhập 2 vai trò (Công nhân trạm QC & Trưởng QC)  
• upload/stream ảnh, agent phát hiện lỗi có khoanh vùng, quyết định PASS/FAIL, giải thích  
• HITL review  
• thống kê lỗi theo lô.

### Nâng cao

• Phân loại nhiều loại lỗi + mức nghiêm trọng  
• agent phân tích xu hướng lỗi theo thời gian/ca và cảnh báo cụm lỗi bất thường  
• đề xuất nguyên nhân  
• ngưỡng tin cậy để tự động chuyển người khi mơ hồ.
