const label = (map: Record<string, string>, code: string) => map[code] ?? code;

const DEFECT_TYPE_LABELS: Record<string, string> = {
  "*": "Mọi loại lỗi",
  scratch: "Trầy xước",
  dent: "Móp",
};

const CHECKLIST_STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bản nháp",
  APPROVED: "Đã duyệt",
  PROPOSED: "Đề xuất",
  REJECTED: "Từ chối",
};

const FINAL_STATUS_LABELS: Record<string, string> = {
  PASS: "Đạt — cho phép chạy thử",
  FAIL: "Không đạt — chuyển sửa chữa (Rework)",
  QUALITY_ALERT_OPEN: "Đang mở cảnh báo chất lượng",
};

const DOCUMENT_STATUS_LABELS: Record<string, string> = {
  REFERENCE_ONLY: "Chỉ tham khảo",
  APPROVED: "Đã duyệt",
};

const ACTION_CODE_LABELS: Record<string, string> = {
  MANUAL_VISUAL_REINSPECTION: "Giữ xe lại và kiểm tra bằng mắt thủ công mới",
  SURFACE_DAMAGE_ASSESSMENT_AND_REINSPECT:
    "Giữ lại để đánh giá bề mặt có kiểm soát và tái kiểm tra",
  ISOLATE_FOR_BODY_REPAIR_ASSESSMENT: "Chuyển sang Sửa chữa thân vỏ để đánh giá kỹ thuật",
  OPEN_UPSTREAM_PROCESS_CHECK: "Mở kiểm tra quy trình đầu nguồn",
};

const EVIDENCE_LABELS: Record<string, string> = {
  controlled_light_reinspection: "Tái kiểm tra dưới ánh sáng kiểm soát",
  defect_extent_measurement: "Đo mức độ lỗi",
  approved_oem_acceptance_criteria: "Tiêu chí chấp nhận OEM đã duyệt",
  approved_geometry_criteria: "Tiêu chí hình học đã duyệt",
  geometry_measurement: "Đo hình học",
  body_repair_signoff: "Xác nhận sửa chữa thân vỏ",
  qc_reinspection: "Tái kiểm tra QC",
  affected_vehicle_list: "Danh sách xe bị ảnh hưởng",
  time_window: "Khung thời gian",
  camera_and_zone_group: "Nhóm camera và khu vực",
  process_owner: "Chủ sở hữu quy trình",
  corrective_action_record: "Hồ sơ hành động khắc phục",
};

const STEP_LABELS: Record<string, string> = {
  CONTAIN_VEHICLE: "Ngăn giữ xe",
  CAPTURE_CONTROLLED_LIGHT_IMAGE: "Chụp ảnh dưới ánh sáng kiểm soát",
  MEASURE_DEFECT_EXTENT: "Đo mức độ lỗi",
  APPLY_APPROVED_OEM_CRITERIA: "Áp dụng tiêu chí OEM đã duyệt",
  QC_SIGN_OFF: "QC ký xác nhận",
  APPLY_HOLD: "Áp dụng giữ xe",
  TRANSFER_TO_BODY_REPAIR_ASSESSMENT: "Chuyển sang đánh giá sửa chữa thân vỏ",
  MEASURE_PANEL_GEOMETRY: "Đo hình học tấm thân xe",
  COMPARE_WITH_APPROVED_DRAWING: "So sánh với bản vẽ đã duyệt",
  QC_REINSPECTION: "Tái kiểm tra QC",
  CONTAIN_AFFECTED_SCOPE: "Ngăn giữ phạm vi bị ảnh hưởng",
  VERIFY_DETECTION_SYSTEM: "Xác minh hệ thống phát hiện",
  CHECK_UPSTREAM_PROCESS: "Kiểm tra quy trình đầu nguồn",
  ASSIGN_OWNER: "Phân công chủ sở hữu",
  RECORD_CORRECTIVE_ACTION: "Ghi nhận hành động khắc phục",
};

export const defectTypeLabel = (code: string) => label(DEFECT_TYPE_LABELS, code);
export const checklistStatusLabel = (code: string) => label(CHECKLIST_STATUS_LABELS, code);
export const finalStatusLabel = (code: string) => label(FINAL_STATUS_LABELS, code);
export const documentStatusLabel = (code: string) => label(DOCUMENT_STATUS_LABELS, code);
export const actionCodeLabel = (code: string) => label(ACTION_CODE_LABELS, code);
export const evidenceLabel = (code: string) => label(EVIDENCE_LABELS, code);
export const stepLabel = (code: string) => label(STEP_LABELS, code);
