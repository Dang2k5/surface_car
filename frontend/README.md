# AI Surface Guardian

Thiết kế và xây dựng web dashboard cho Nhân viên Trạm QC bề mặt thân vỏ ô tô, tập trung vào việc kiểm tra lỗi xước, móp bằng hệ thống Computer Vision + AI Agent, hỗ trợ HITL (Human-in-the-Loop) và giám sát lỗi theo thời gian thực.

1. Vai trò người dùng

Đây là giao diện dành riêng cho Nhân viên QC tại một trạm kiểm tra, không phải giao diện quản lý trưởng ca.

Nhân viên có nhiệm vụ:

Theo dõi trạng thái ca làm việc.

Theo dõi số lượng xe đang chờ/đã kiểm.

Thực hiện inspection khi xe đến trạm.

Xem kết quả phán quyết của AI Agent.

Xử lý các case AI không đủ tự tin → HITL.

Theo dõi cảnh báo lỗi lặp theo realtime.

Tra cứu lịch sử inspection.

Thiết kế giao diện theo phong cách industrial automotive / smart factory / AI inspection, chuyên nghiệp, trực quan, ưu tiên khả năng đọc nhanh trong môi trường nhà máy.

2. Layout tổng thể

Sử dụng layout dashboard desktop:

Sidebar trái cố định

Logo + tên hệ thống: AUTO QC

Tổng quan ca

Inspection

Hàng đợi HITL

Cảnh báo realtime

Lịch sử inspection

Phía dưới sidebar:

Trạng thái kết nối hệ thống: AI ONLINE

Camera: 5/5 ONLINE

Tên nhân viên

Trạm hiện tại: Station QC-03

Nút đăng xuất

Topbar

Tên trạm: QC Surface Inspection — Station 03

Mã ca: SHIFT A

Thời gian hiện tại

Trạng thái hệ thống

Notification icon

Avatar nhân viên

Phong cách UI:

Dark mode làm chủ đạo.

Background charcoal/near-black.

Card màu dark gray.

Accent màu amber/orange cho trạng thái cảnh báo.

Green cho PASS.

Red cho FAIL.

Blue/cyan cho AI/system information.

Typography rõ ràng, số liệu lớn.

Border mảnh, bo góc vừa phải.

Có subtle glow cho các trạng thái realtime.

Không sử dụng quá nhiều gradient hoặc hiệu ứng gây rối mắt.

3. Trang Tổng quan ca QC

Đây là màn hình mặc định sau khi nhân viên đăng nhập.

Header

Hiển thị:

QC SHIFT OVERVIEW

Thông tin:

Station: QC-03

Shift: 07:00 — 15:00

Operator: Nguyễn Văn A

Shift status: ACTIVE

KPI cards

Tạo 5 card lớn:

1. Trạng thái ca

ACTIVE

Thời gian đã làm: 04h 32m

Remaining: 03h 28m

2. Xe đã kiểm

128

+12% vs previous shift

3. PASS

116

90.6%

4. FAIL

12

9.4%

5. HITL Pending

4

Hiển thị màu amber nếu còn case chưa xử lý.

Khu vực "Live Inspection"

Hiển thị trạng thái hiện tại:

CURRENT VEHICLE

Ví dụ:

VIN: VF8-2026-001284

Status:

INSPECTION IN PROGRESS

Progress:

Camera 3 / 5

Timeline:

Vehicle detected → Capture → AI Inspection → Decision

Có animation nhẹ thể hiện hệ thống đang xử lý.

Camera status

Hiển thị 5 camera:

Camera 01 — Front

Camera 02 — Rear

Camera 03 — Left

Camera 04 — Right

Camera 05 — Top/Rear perspective

Mỗi camera có:

Online/offline

Last capture

FPS

Image capture status

Ví dụ:

CAM 01 — ONLINE

CAM 02 — ONLINE

CAM 03 — ONLINE

CAM 04 — ONLINE

CAM 05 — ONLINE

Cảnh báo cần chú ý

Một panel bên phải:

ATTENTION REQUIRED

Ví dụ:

🔴 3 repeated scratches detected

🟠 2 HITL cases waiting

🟠 Camera 04 confidence degradation

🟢 All systems operational

4. Trang Inspection — chức năng quan trọng nhất

Khi xe đi đến trạm, hệ thống tự động nhận diện xe và bắt đầu inspection.

Thiết kế màn hình theo kiểu command center.

Header

VEHICLE INSPECTION

Thông tin xe:

VIN

Model

Production line

Station

Inspection ID

Timestamp

Ví dụ:

VF8 | VIN: VF8-2026-001284 | Inspection #QC-0001284

5. Khu vực 5 camera

Chia màn hình thành layout lớn:

Camera grid

5 camera:

┌──────────────────┬──────────────────┐
│                  │                  │
│   CAMERA 01      │   CAMERA 02      │
│   FRONT          │   REAR           │
│                  │                  │
├──────────────────┼──────────────────┤
│                  │                  │
│   CAMERA 03      │   CAMERA 04      │
│   LEFT           │   RIGHT          │
│                  │                  │
├──────────────────┴──────────────────┤
│                                    │
│            CAMERA 05               │
│         TOP / OVERVIEW             │
│                                    │
└────────────────────────────────────┘


Mỗi camera feed hiển thị:

Camera ID

Live/Captured

timestamp

FPS

confidence

camera health

nút zoom

Khi AI phát hiện lỗi, overlay bounding box lên vùng lỗi.

Ví dụ:

SCRATCH #03

Confidence: 96.4%

6. AI Agent Decision Panel

Bên phải màn hình hiển thị quyết định của AI Agent.

Title:

AI AGENT DECISION

Trạng thái lớn:

PASS

hoặc

FAIL

hoặc

NEED HUMAN REVIEW

Hiển thị:

Agent confidence

Defect count

Defect type

Severity

Affected area

Camera source

Reasoning summary

Ví dụ:

DECISION
FAIL

Confidence
97.8%

Detected defects
3

Scratch
2

Dent
1

Severity
MEDIUM


Không hiển thị chain-of-thought nội bộ của Agent. Chỉ hiển thị explanation ngắn gọn, có cấu trúc và có thể audit.

Ví dụ:

Vehicle rejected because 2 scratches exceeded the configured surface-defect threshold on the left door.

7. Defect Detail

Khi click vào một lỗi:

Hiển thị ảnh crop vùng lỗi.

Thông tin:

DEFECT #02

Type: Scratch

Location: Left Door

Severity: Major

Confidence: 96.8%

Camera: CAM-03

Bounding box

Measurement: 18.4 mm

Threshold: > 15 mm

Decision: FAIL

Cho phép nhân viên:

Zoom

View original image

View defect crop

Compare with reference image

8. HITL Queue

Tạo một trang riêng:

HUMAN REVIEW QUEUE

Hiển thị những case AI Agent không thể tự quyết định với confidence đủ cao.

Mỗi case:

QC-0001281
VIN: VF8-2026-001281

Issue:
Possible Scratch

AI Confidence:
62.4%

Reason:
Ambiguous reflection

Waiting:
02:14


Có filter:

All

Pending

In Review

Resolved

Priority:

Critical

High

Medium

Low

Khi nhân viên mở case:

AI suggestion

NEED HUMAN REVIEW

Hiển thị ảnh xe + crop defect + AI prediction.

Nhân viên có 3 lựa chọn lớn:

CONFIRM FAIL

CONFIRM PASS

REVIEW / ESCALATE

Bắt buộc nhập reason khi override AI decision.

Ví dụ:

Human decision: FAIL

Reason: Scratch clearly visible under inspection lighting.

Sau khi xác nhận, case chuyển sang RESOLVED.

9. Cảnh báo sớm lỗi lặp — Realtime

Trang:

EARLY DEFECT WARNING

Mục tiêu là phát hiện pattern lỗi lặp lại trên nhiều xe, thay vì chỉ cảnh báo từng xe riêng lẻ.

Ví dụ:

🔴 REPEATED DEFECT DETECTED

Scratch detected on Left Door

Occurrences: 7
Last 20 vehicles: 7
Trend: ↑ Increasing

Vehicle IDs:
VF8-001278
VF8-001280
VF8-001281
VF8-001284
...


Hiển thị biểu đồ realtime:

Defect frequency / vehicle

Các loại:

Scratch

Dent

Paint defect

Other surface anomaly

Có các mức:

NORMAL

WATCH

WARNING

CRITICAL

Ví dụ:

7 scratches detected at the same body location within the last 20 vehicles.

Có nút:

VIEW AFFECTED VEHICLES

VIEW DEFECT IMAGES

MARK AS INVESTIGATING

10. Lịch sử Inspection

Trang:

INSPECTION HISTORY

Bảng dữ liệu:

TimeVINModelResultDefectsAI ConfidenceOperator10:42:18VF8-001284VF8FAIL397.8%Nguyễn A10:40:02VF8-001283VF8PASS099.2%Nguyễn A10:38:44VF8-001282VF8HITL161.4%Nguyễn A

Filter:

Date/time

VIN

Model

PASS/FAIL/HITL

Defect type

Severity

Confidence range

Click vào một inspection → mở Inspection Detail với toàn bộ:

5 camera images

AI detections

Decision

Confidence

Human decision nếu có

Timestamp

Inspection ID

Audit trail

11. Realtime system status

Luôn hiển thị trên UI:

AI ENGINE       ● ONLINE
CAMERAS         5/5 ONLINE
VISION MODEL    ● READY
AGENT           ● READY
DATABASE        ● CONNECTED


Nếu có lỗi:

CAMERA 04       ● OFFLINE


thì chuyển sang trạng thái cảnh báo và hiển thị notification.

12. UX quan trọng

Thiết kế dành cho nhân viên nhà máy nên ưu tiên:

Nhìn là hiểu ngay trạng thái.

Ít thao tác.

PASS/FAIL/HITL phải cực kỳ rõ ràng.

Các cảnh báo quan trọng phải nổi bật nhưng không gây overload.

Realtime data phải có timestamp.

Các quyết định của AI phải có confidence và evidence.

Human override phải được audit.

Không để nhân viên phải mở quá nhiều modal.

Hỗ trợ màn hình desktop độ phân giải 1920×1080.

Responsive ở mức hợp lý nhưng ưu tiên desktop industrial monitor.

13. Animation

Sử dụng animation vừa phải với Framer Motion.

Các animation:

Camera capture → subtle pulse.

AI processing → animated progress.

New vehicle → slide/fade transition.

New HITL case → amber pulse.

Critical warning → subtle red pulse.

PASS → smooth green status transition.

FAIL → red status transition.

Realtime defect chart → smooth update.

Không sử dụng animation quá mạnh vì đây là giao diện vận hành sản xuất, không phải marketing website.

14. Công nghệ

Build bằng:

React

Vite

TypeScript

Tailwind CSS

Framer Motion

Lucide React

Recharts cho charts

Tạo component có cấu trúc rõ ràng:

Dashboard
├── ShiftOverview
├── Inspection
│   ├── VehicleHeader
│   ├── CameraGrid
│   ├── DefectOverlay
│   └── AgentDecision
├── HITLQueue
├── EarlyWarnings
├── InspectionHistory
└── SystemStatus


Sử dụng mock data nhưng kiến trúc component phải sẵn sàng để kết nối WebSocket/API realtime sau này.

15. Visual direction

Phong cách tổng thể:

"AI-powered automotive factory control room"

Tham khảo cảm giác của:

Automotive production line

Computer vision inspection system

Mission control dashboard

Industrial SCADA/HMI hiện đại

AI operations center

Không thiết kế giống dashboard SaaS thông thường.

Giao diện phải tạo cảm giác:

"Đây là hệ thống AI đang trực tiếp kiểm soát chất lượng thân vỏ xe trong nhà máy."

Ưu tiên data density vừa phải, visual hierarchy mạnh, trạng thái realtime rõ ràng, evidence-based AI decision và khả năng xử lý HITL nhanh chóng.

Hãy xây dựng giao diện hoàn chỉnh với mock data thực tế, các trạng thái PASS/FAIL/HITL/WARNING, tương tác giữa các màn hình và animation realtime để có thể demo trực tiếp như một hệ thống QC AI production-ready.

This project was built with [Lovable](https://lovable.dev).

**Live app**: https://ai-auto-guard.lovable.app

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/e1aae7c7-528a-49b8-9cde-5ada6047bfc9).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
