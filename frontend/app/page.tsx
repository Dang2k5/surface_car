'use client';
/* eslint-disable @next/next/no-img-element */

import { useCallback, useEffect, useState } from 'react';

type Lang = 'vi' | 'en';
type View = 'overview' | 'inspect' | 'queue' | 'catalog' | 'alerts' | 'history';
type TraceEvent = { node: string; status: string; detail: string };
type LiveEvent = TraceEvent & {
  id: number;
  phase: 'running' | 'completed' | 'waiting';
};
type PolicyReference = {
  id: string;
  document_family: string;
  revision: string;
  section: string;
  effective_date?: string | null;
  expiry_date?: string | null;
  document_status: string;
  title: string;
  scope: string;
  url: string;
};
type PolicyDocumentReview = {
  query: Record<string, string>;
  roles_completed: string[];
  matched_document_count: number;
  extracted_conditions: string[];
  evidence_comparison: Array<{ evidence: string; available: boolean }>;
  missing_data: string[];
  checklist_status: string;
  approved_checklist: string[];
  proposed_checklist: string[];
  citations: PolicyReference[];
  warnings: Array<{ code: string; severity: string; message: string; document_id?: string | null }>;
};
type QCState = {
  thread_id: string;
  inspection_id: string;
  vehicle_id: string;
  vehicle_model: string;
  image_url: string;
  camera_id: string;
  zone_name: string;
  defect_detected?: boolean;
  defect_type?: string;
  confidence?: number;
  bbox?: { x1: number; y1: number; x2: number; y2: number } | null;
  segmentation_result?: { format: string; points: number[][] } | null;
  visual_measurements?: {
    width_px: number;
    height_px: number;
    bbox_area_px: number;
    image_area_ratio: number;
    center_x_ratio: number;
    center_y_ratio: number;
    relative_position: string;
    physical_size_status: string;
    estimated_width_mm?: number;
    estimated_height_mm?: number;
    estimated_length_mm?: number;
    estimated_bbox_area_mm2?: number;
    estimated_mask_area_mm2?: number | null;
    calibration_profile_id?: string;
  };
  detections?: Array<{
    class_name: string;
    raw_class_name: string;
    confidence: number;
    bbox: { x1: number; y1: number; x2: number; y2: number };
  }>;
  enriched_defects?: Array<Record<string, unknown>>;
  image_width?: number;
  image_height?: number;
  model_name?: string;
  model_version?: string;
  model_task?: string;
  inference_ms?: number;
  inference_status?: string;
  severity?: string;
  decision?: string;
  reason?: string;
  verify_count?: number;
  verify_result?: string;
  human_required?: boolean;
  human_decision?: { action: string; reviewer: string; reason: string };
  qc_decision_record?: QCDecisionRecord;
  suggested_defect_codes?: DefectCode[];
  classified_defect_code?: string | null;
  defect_family?: string | null;
  similar_defect_warning?: boolean;
  defect_code_classification?: {
    confidence: number;
    rationale_vi: string;
    provider: string;
    candidate_codes: string[];
  };
  recommendation_code?: string;
  recommendation?: string;
  policy_decision?: {
    policy_id: string;
    policy_revision: string;
    policy_status: string;
    approval_scope: string;
    policy_title: string;
    test_drive_allowed: boolean | null;
    human_required: boolean;
    required_steps: string[];
    missing_evidence: string[];
    production_eligible: boolean;
    references: PolicyReference[];
    document_review: PolicyDocumentReview;
  };
  ai_analysis?: {
    summary_en: string;
    summary_vi: string;
    risk_flags: string[];
    recommended_checks: string[];
    cited_source_ids: string[];
    provider: string;
    model: string;
    fallback_reason?: string | null;
  };
  final_status?: string;
  allow_test_drive?: boolean;
  hitl_status?: 'PENDING' | 'CONFIRMED' | 'OVERRIDDEN';
  execution_trace?: TraceEvent[];
};
type GraphRun = {
  thread_id: string;
  status: 'COMPLETED' | 'INTERRUPTED';
  state: QCState;
  interrupt?: { reason?: string; allowed_actions?: string[] };
};
type GraphSpec = { nodes: string[]; checkpointer: string; mermaid: string };
type AgentStatus = {
  langgraph: string;
  checkpointer: string;
  reasoning: {
    mode: string;
    provider: string;
    requested_provider: string;
    api_key_configured: boolean;
    llm_accessed: boolean;
    last_call_status: string;
    last_success_at?: string | null;
    last_error?: string | null;
  };
  agent_analysis?: Record<string, unknown>;
};
type UploadedEvidence = {
  file: File;
  previewUrl: string;
  vehicleId: string;
  vehicleModel: string;
  cameraId: string;
  zoneName: string;
};
type DefectCode = {
  defect_code: string;
  defect_type: string;
  cv_label: string;
  defect_family: string;
  display_name: string;
  description: string;
  classification_rule: string;
  default_severity: string;
  measurement_required: number;
  active: number;
};
type DefectCodeInput = {
  defect_code: string;
  defect_type: string;
  cv_label: string;
  defect_family: string;
  display_name: string;
  description: string;
  classification_rule: string;
  default_severity: string;
  measurement_required: boolean;
  active: boolean;
};
type QCDecisionRecord = {
  decision_id: string;
  inspection_id: string;
  vehicle_id: string;
  defect_code: string;
  defect_type: string;
  location: string;
  length_mm: number | null;
  severity: string;
  action: string;
  disposition: string;
  reviewer: string;
  created_at: string;
};
type QCFormState = {
  defectCode: string;
  severity: string;
  disposition: 'PASS' | 'HOLD' | 'REWORK' | 'REINSPECT';
  reviewer: string;
  location: string;
  lengthMm: string;
  notes: string;
};
type InspectionFinding = {
  inspection_id: string;
  thread_id: string;
  vehicle_id: string;
  inspected_at: string;
  defect_type: string;
  classified_defect_code: string;
  defect_family: string;
  zone_name: string;
  camera_id: string;
  confidence: number;
  severity: string;
  decision: string;
  final_status: string;
  recommendation_code: string;
  recommendation: string;
  image_url: string;
};
type DefectAggregate = {
  defect_type: string;
  occurrence_count: number;
  affected_vehicle_count: number;
  zones: string[];
  camera_ids: string[];
  average_confidence: number;
  maximum_confidence: number;
  first_seen: string;
  last_seen: string;
};
type QualityAlert = {
  id: string;
  severity: 'WARNING' | 'CRITICAL';
  status: string;
  defect_type: string;
  zone_name: string;
  camera_id: string;
  occurrence_count: number;
  affected_vehicle_count: number;
  affected_vehicle_ids: string[];
  related_defect_codes: string[];
  similar_code_warning: boolean;
  average_confidence: number;
  maximum_confidence: number;
  first_seen: string;
  last_seen: string;
  window_hours: number;
  window_size: number;
  consecutive_count: number;
  trigger_type: string;
  predicted_root_cause: string;
  upstream_target_shop: string;
  actionable_routing_command: string;
  message_en: string;
  message_vi: string;
  recommendation_en: string;
  recommendation_vi: string;
  upstream_checks_en: string[];
  upstream_checks_vi: string[];
  occurrences: InspectionFinding[];
  policy_decision: QCState['policy_decision'];
  ai_analysis: QCState['ai_analysis'];
};
type QualityAlertSummary = {
  generated_at: string;
  window_hours: number;
  window_size: number;
  minimum_occurrences: number;
  in_window_threshold: number;
  analyzed_inspections: number;
  defect_breakdown: DefectAggregate[];
  findings: InspectionFinding[];
  alerts: QualityAlert[];
};

const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';
const apiFetch = (path: string, timeoutMs = 8000) =>
  fetch(`${API}${path}`, { signal: AbortSignal.timeout(timeoutMs) });
async function modelFrameFromFile(file: File): Promise<File> {
  if (!file.type.startsWith('video/')) return file;
  const source = URL.createObjectURL(file);
  try {
    const video = document.createElement('video');
    video.muted = true;
    video.preload = 'auto';
    video.src = source;
    await new Promise<void>((resolve, reject) => {
      video.onloadeddata = () => resolve();
      video.onerror = () => reject(new Error('Cannot read the primary camera video.'));
    });
    const targetTime = Number.isFinite(video.duration) && video.duration > 0
      ? video.duration / 2
      : 0;
    if (targetTime > 0) {
      await new Promise<void>((resolve, reject) => {
        video.onseeked = () => resolve();
        video.onerror = () => reject(new Error('Cannot extract a frame from the video.'));
        video.currentTime = targetTime;
      });
    }
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d')?.drawImage(video, 0, 0);
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (value) => value ? resolve(value) : reject(new Error('Cannot encode the inspection frame.')),
        'image/jpeg',
        0.92,
      ),
    );
    return new File([blob], `${file.name.replace(/\.[^.]+$/, '')}-inspection-frame.jpg`, {
      type: 'image/jpeg',
    });
  } finally {
    URL.revokeObjectURL(source);
  }
}
const NAV: {
  id: View;
  icon: string;
  en: string;
  vi: string;
  hintEn: string;
  hintVi: string;
}[] = [
  {
    id: 'overview',
    icon: '⌂',
    en: 'Overview',
    vi: 'Tổng quan',
    hintEn: 'Shift status',
    hintVi: 'Trạng thái ca',
  },
  {
    id: 'inspect',
    icon: '◎',
    en: 'Agent inspection',
    vi: 'Kiểm tra bằng Agent',
    hintEn: 'Primary workflow',
    hintVi: 'Quy trình chính',
  },
  {
    id: 'queue',
    icon: '!',
    en: 'QC review',
    vi: 'Hàng đợi QC',
    hintEn: 'Human decisions',
    hintVi: 'Quyết định QC',
  },
  {
    id: 'catalog',
    icon: '◇',
    en: 'Defect registry',
    vi: 'Sổ mã lỗi QC',
    hintEn: 'Codes and measurements',
    hintVi: 'Mã lỗi và số đo',
  },
  {
    id: 'alerts',
    icon: '△',
    en: 'Trend alerts',
    vi: 'Cảnh báo lặp lỗi',
    hintEn: 'Upstream checks',
    hintVi: 'Kiểm tra khâu trước',
  },
  {
    id: 'history',
    icon: '▤',
    en: 'History',
    vi: 'Lịch sử',
    hintEn: 'Audit trail',
    hintVi: 'Dấu vết audit',
  },
];
const NODE_COPY: Record<string, readonly [string, string]> = {
  prepare_input: ['Prepare input', 'Chuẩn hóa đầu vào'],
  detect_defect: ['Detect defect', 'Phát hiện lỗi'],
  assess_result: ['Assess result', 'Đánh giá kết quả'],
  verify_defect: ['Verify defect', 'Xác minh lại'],
  human_review: ['Human review', 'QC xác nhận'],
  generate_recommendation: ['Generate action', 'Tạo phương án xử lý'],
  save_result: ['Save result', 'Lưu kết quả'],
};
const ACTION_COPY: Record<string, readonly [string, string]> = {
  RELEASE_TO_NEXT_QUALITY_GATE: [
    'Release to the next quality gate',
    'Cho xe đi tiếp tới cổng chất lượng kế tiếp',
  ],
  SURFACE_POLISH_AND_REINSPECT: [
    'Polish affected surface, then reinspect',
    'Đánh bóng vùng bị ảnh hưởng, sau đó kiểm tra lại',
  ],
  SURFACE_DAMAGE_ASSESSMENT_AND_REINSPECT: [
    'Hold for controlled surface assessment and reinspection',
    'Giữ xe để đánh giá bề mặt và kiểm tra lại có kiểm soát',
  ],
  ISOLATE_FOR_BODY_REPAIR_ASSESSMENT: [
    'Hold and transfer to Body Repair',
    'Giữ xe và chuyển Bộ phận sửa chữa thân vỏ',
  ],
  MANUAL_VISUAL_REINSPECTION: [
    'Hold for a new manual inspection',
    'Giữ xe để kiểm tra ngoại quan thủ công lại',
  ],
  ISOLATE_FOR_GLASS_REPAIR: [
    'Hold and transfer for glass damage assessment',
    'Giữ xe và chuyển đánh giá hư hỏng kính',
  ],
  ISOLATE_FOR_LIGHTING_REPAIR: [
    'Hold and transfer for lighting system repair',
    'Giữ xe và chuyển sửa chữa hệ thống đèn',
  ],
  IMMOBILIZE_FOR_TIRE_SERVICE: [
    'Immobilize and transfer for tire service',
    'Cố định xe và chuyển xử lý lốp',
  ],
};

const wait = (ms: number) =>
  new Promise((resolve) => window.setTimeout(resolve, ms));
const local = (
  pair: readonly [string, string] | undefined,
  lang: Lang,
  fallback = '—',
) => pair?.[lang === 'vi' ? 1 : 0] || fallback;
const percent = (value?: number) => `${Math.round((value || 0) * 100)}%`;
const pretty = (value?: string) => (value ? value.replaceAll('_', ' ') : '—');
const policyStepLabel = (value: string, lang: Lang) => {
  const labels: Record<string, readonly [string, string]> = {
    CONTAIN_VEHICLE: ['Contain vehicle', 'Giữ xe trong khu vực kiểm soát'],
    CAPTURE_CONTROLLED_LIGHT_IMAGE: ['Capture controlled-light evidence', 'Chụp evidence dưới ánh sáng kiểm soát'],
    MEASURE_DEFECT_EXTENT: ['Measure defect extent', 'Đo phạm vi lỗi'],
    APPLY_APPROVED_OEM_CRITERIA: ['Apply approved OEM criteria', 'Đối chiếu tiêu chí OEM đã phê duyệt'],
    QC_SIGN_OFF: ['Record QC sign-off', 'QC xác nhận và ký duyệt'],
    APPLY_HOLD: ['Apply vehicle hold', 'Áp dụng trạng thái giữ xe'],
    TRANSFER_TO_BODY_REPAIR_ASSESSMENT: ['Transfer to Body Repair assessment', 'Chuyển đánh giá Body Repair'],
    MEASURE_PANEL_GEOMETRY: ['Measure defect geometry', 'Đo hình học vùng lỗi'],
    COMPARE_WITH_APPROVED_DRAWING: ['Compare with approved drawing', 'Đối chiếu bản vẽ đã phê duyệt'],
    QC_REINSPECTION: ['Perform QC reinspection', 'QC kiểm tra lại'],
  };
  return local(labels[value], lang, pretty(value));
};
const policyWarningLabel = (code: string, fallback: string, lang: Lang) => {
  if (lang === 'en') return fallback;
  const labels: Record<string, string> = {
    POLICY_QUERY_CONTEXT_INCOMPLETE: 'Thiếu model xe hoặc loại lỗi để tìm đúng tài liệu.',
    DOCUMENT_NOT_APPROVED_FOR_PLANT_USE: 'Tài liệu chỉ dùng tham chiếu, chưa được nhà máy phê duyệt để quyết định release.',
    EFFECTIVE_DATE_UNCONFIRMED: 'Chưa xác nhận ngày hiệu lực trong danh mục tài liệu kiểm soát.',
    DOCUMENT_EXPIRED: 'Tài liệu đã hết hiệu lực; không được dùng để đưa ra quyết định.',
    REVISION_CONFLICT: 'Có nhiều revision cùng phù hợp; cần Quality Engineering xác nhận bản có hiệu lực.',
    CHECKLIST_NOT_APPROVED: 'Checklist hiện là bản đề xuất, chưa phải checklist nhà máy đã phê duyệt.',
    NO_APPROVED_CONTROLLED_DOCUMENT: 'Không tìm thấy tài liệu policy kiểm soát đã được phê duyệt cho ngữ cảnh này.',
  };
  return labels[code] || fallback;
};
const actionLabel = (state: QCState | undefined, lang: Lang) => {
  const code =
    state?.recommendation_code ||
    (state?.recommendation && ACTION_COPY[state.recommendation]
      ? state.recommendation
      : '');
  return local(
    ACTION_COPY[code],
    lang,
    state?.recommendation || pretty(state?.decision),
  );
};
const outcomeTone = (run?: GraphRun) =>
  run?.status === 'INTERRUPTED'
    ? 'amber'
    : run?.state.final_status === 'PASS'
      ? 'green'
      : run
        ? 'red'
        : 'neutral';

const defectLabel = (state: QCState, lang: Lang) => {
  if (!state.defect_detected) return lang === 'vi' ? 'Không xác nhận lỗi' : 'No confirmed defect';
  const labels: Record<string, readonly [string, string]> = {
    dent: ['Dent', 'Vết móp'],
    scratch: ['Scratch', 'Vết xước'],
    crack: ['Crack', 'Vết nứt'],
    glass_shatter: ['Glass damage', 'Kính vỡ'],
    lamp_broken: ['Broken lamp', 'Đèn hư hỏng'],
    tire_flat: ['Flat tire', 'Lốp xẹp'],
  };
  return local(labels[state.defect_type || ''], lang, pretty(state.defect_type));
};

const finalRouteLabel = (run: GraphRun, lang: Lang) => {
  if (run.status === 'INTERRUPTED') return lang === 'vi' ? 'Giữ tại trạm QC' : 'Hold at QC station';
  const labels: Record<string, readonly [string, string]> = {
    PASS: ['Next quality gate', 'Cổng chất lượng kế tiếp'],
    CONTROLLED_REPAIR: ['Controlled surface rework', 'Khu sửa bề mặt có kiểm soát'],
    HOLD_FOR_REWORK: ['Body Repair assessment', 'Khu đánh giá sửa chữa thân vỏ'],
    HOLD_FOR_QC: ['QC reinspection bay', 'Khu kiểm tra lại QC'],
  };
  return local(labels[run.state.final_status || ''], lang, pretty(run.state.final_status));
};

function decisionGuide(run: GraphRun, lang: Lang) {
  const code = run.state.recommendation_code || '';
  if (run.status === 'INTERRUPTED' || code === 'MANUAL_VISUAL_REINSPECTION') {
    return {
      testDrive: lang === 'vi' ? 'TẠM KHÓA' : 'BLOCKED',
      releaseGate: lang === 'vi' ? 'QC xác nhận trực tiếp và resume workflow' : 'QC confirmation and workflow resume',
      policy: lang === 'vi' ? 'Kết quả dưới ngưỡng an toàn hoặc vẫn mơ hồ sau xác minh.' : 'Result is below the safety threshold or remains uncertain after verification.',
      steps: lang === 'vi'
        ? ['Giữ xe tại trạm QC và khóa luồng release.', 'Chụp lại dưới ánh sáng kiểm soát hoặc camera bổ sung.', 'QC xác nhận loại lỗi, mức độ và vùng quan sát.', 'Resume đúng thread để Agent hoàn tất điều phối.']
        : ['Hold the vehicle at QC and block release.', 'Recapture under controlled light or a secondary camera.', 'Confirm defect type, severity, and inspection zone.', 'Resume the same thread to complete routing.'],
    };
  }
  if (
    code === 'SURFACE_POLISH_AND_REINSPECT' ||
    code === 'SURFACE_DAMAGE_ASSESSMENT_AND_REINSPECT'
  ) {
    return {
      testDrive: lang === 'vi' ? 'KHÓA ĐẾN KHI KIỂM TRA LẠI' : 'BLOCKED UNTIL REINSPECTION',
      releaseGate: lang === 'vi' ? 'QC xác nhận bề mặt đạt sau xử lý' : 'QC accepts surface after treatment',
      policy: lang === 'vi' ? 'Lỗi bề mặt đã được xác nhận và đủ điều kiện xử lý có kiểm soát.' : 'Confirmed surface defect eligible for controlled treatment.',
      steps: lang === 'vi'
        ? ['Bảo vệ trim và làm sạch vùng ảnh hưởng.', 'Đánh bóng theo hướng dẫn công việc được phê duyệt.', 'Kiểm tra lại dưới ánh sáng kiểm soát.', 'Ghi kết quả và chỉ release sau khi QC xác nhận.']
        : ['Protect trim and clean the affected area.', 'Polish under the approved work instruction.', 'Reinspect under controlled lighting.', 'Record the result and release only after QC confirmation.'],
    };
  }
  if (code === 'ISOLATE_FOR_BODY_REPAIR_ASSESSMENT') {
    return {
      testDrive: lang === 'vi' ? 'CẤM TEST DRIVE' : 'DO NOT TEST DRIVE',
      releaseGate: lang === 'vi' ? 'Body Repair đánh giá, sửa chữa và QC kiểm tra lại' : 'Body Repair assessment, repair, and QC reinspection',
      policy: lang === 'vi' ? 'Vết móp được xác nhận ở confidence cao; xe phải được cô lập để đánh giá hình học vùng lỗi.' : 'High-confidence dent requires isolation and defect geometry assessment.',
      steps: lang === 'vi'
        ? ['Gắn trạng thái HOLD và khóa test drive.', 'Chuyển xe tới khu đánh giá Body Repair.', 'Đo hình học vùng lỗi và đánh giá khả năng sửa chữa.', 'Thực hiện repair theo hướng dẫn đã phê duyệt.', 'QC kiểm tra lại và ghi nhận trước khi release.']
        : ['Apply HOLD and block test drive.', 'Transfer to Body Repair assessment.', 'Measure defect geometry and repairability.', 'Repair under an approved instruction.', 'QC reinspects and records acceptance before release.'],
    };
  }
  if (
    code === 'ISOLATE_FOR_GLASS_REPAIR' ||
    code === 'ISOLATE_FOR_LIGHTING_REPAIR' ||
    code === 'IMMOBILIZE_FOR_TIRE_SERVICE'
  ) {
    return {
      testDrive: lang === 'vi' ? 'CẤM DI CHUYỂN XE' : 'VEHICLE MOVEMENT BLOCKED',
      releaseGate: lang === 'vi' ? 'Chuyên viên xác nhận sửa chữa và QC kiểm tra lại' : 'Specialist repair confirmation and QC reinspection',
      policy: lang === 'vi' ? 'Lỗi an toàn được model phát hiện; xe phải được cô lập để đánh giá chuyên môn.' : 'A safety-related defect was detected; specialist assessment is required.',
      steps: lang === 'vi'
        ? ['Áp dụng HOLD và cố định xe tại vị trí an toàn.', 'Chuyển evidence và thông tin lỗi tới bộ phận chuyên môn.', 'Thực hiện sửa chữa theo hướng dẫn được phê duyệt.', 'QC kiểm tra lại trước khi release.']
        : ['Apply HOLD and immobilize the vehicle safely.', 'Transfer evidence to the responsible specialist.', 'Repair under an approved instruction.', 'QC reinspects before release.'],
    };
  }
  return {
    testDrive: lang === 'vi' ? 'THEO QUY ĐỊNH TRẠM' : 'PER STATION POLICY',
    releaseGate: lang === 'vi' ? 'Không có lỗi được xác nhận' : 'No confirmed defect',
    policy: lang === 'vi' ? 'Không phát hiện lỗi thân vỏ đủ điều kiện tạo HOLD.' : 'No body defect meets the HOLD criteria.',
    steps: lang === 'vi'
      ? ['Ghi kết quả PASS vào audit.', 'Xác nhận evidence và Vehicle ID.', 'Chuyển xe tới cổng chất lượng kế tiếp.']
      : ['Record PASS in the audit.', 'Confirm evidence and Vehicle ID.', 'Route to the next quality gate.'],
  };
}

export default function Home() {
  const [lang, setLang] = useState<Lang>('vi');
  const [view, setView] = useState<View>('overview');
  const [runs, setRuns] = useState<GraphRun[]>([]);
  const [graph, setGraph] = useState<GraphSpec | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [activeRun, setActiveRun] = useState<GraphRun | null>(null);
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [uploadedEvidence, setUploadedEvidence] = useState<UploadedEvidence | null>(null);
  const [defectCodes, setDefectCodes] = useState<DefectCode[]>([]);
  const [qcDecisions, setQcDecisions] = useState<QCDecisionRecord[]>([]);
  const [qcForm, setQcForm] = useState<QCFormState>({
    defectCode: '',
    severity: 'UNASSESSED',
    disposition: 'HOLD',
    reviewer: 'qc-inspector-01',
    location: '',
    lengthMm: '',
    notes: '',
  });
  const [alertSummary, setAlertSummary] = useState<QualityAlertSummary | null>(null);
  const [notice, setNotice] = useState('Đang kết nối workstation…');
  const [humanReason, setHumanReason] = useState(
    'Đã xác nhận trực tiếp dưới ánh sáng kiểm soát.',
  );
  const t = useCallback(
    (en: string, vi: string) => (lang === 'vi' ? vi : en),
    [lang],
  );
  const displayRuns = Array.from(
    new Map(runs.map((item) => [item.state.vehicle_id, item])).values(),
  );
  const waitingRuns = displayRuns.filter((item) => item.status === 'INTERRUPTED');
  const completedRuns = displayRuns.filter((item) => item.status === 'COMPLETED');
  const passCount = completedRuns.filter(
    (item) => item.state.final_status === 'PASS',
  ).length;
  const holdCount = completedRuns.filter(
    (item) => item.state.final_status && item.state.final_status !== 'PASS',
  ).length;

  const load = useCallback(async () => {
    try {
      const [graphResponse, agentStatusResponse] = await Promise.all([
        apiFetch('/agent/graph'),
        apiFetch('/agent/status'),
      ]);
      if (!graphResponse.ok || !agentStatusResponse.ok)
        throw new Error('Backend unavailable');
      setGraph((await graphResponse.json()) as GraphSpec);
      setAgentStatus((await agentStatusResponse.json()) as AgentStatus);
      setBackendOnline(true);
      setNotice(
        t(
          'Workstation connected. Connect the primary camera to start.',
          'Đã kết nối workstation. Hãy kết nối camera chính để bắt đầu.',
        ),
      );
      const secondary = await Promise.allSettled([
        apiFetch('/agent/runs'),
        apiFetch('/api/quality-alerts'),
        apiFetch('/api/qc/defect-codes'),
        apiFetch('/api/qc/decisions'),
      ]);
      const responseAt = (index: number) => secondary[index].status === 'fulfilled'
        ? secondary[index].value
        : null;
      const runResponse = responseAt(0);
      const alertResponse = responseAt(1);
      const defectCodeResponse = responseAt(2);
      const qcDecisionResponse = responseAt(3);
      if (runResponse?.ok) setRuns((await runResponse.json()) as GraphRun[]);
      if (alertResponse?.ok) setAlertSummary((await alertResponse.json()) as QualityAlertSummary);
      if (defectCodeResponse?.ok) setDefectCodes((await defectCodeResponse.json()) as DefectCode[]);
      if (qcDecisionResponse?.ok) setQcDecisions((await qcDecisionResponse.json()) as QCDecisionRecord[]);
    } catch {
      setBackendOnline(false);
      setNotice(
        t(
          'Cannot reach FastAPI on port 8000.',
          'Không kết nối được FastAPI tại cổng 8000.',
        ),
      );
    }
  }, [t]);

  useEffect(() => {
    // Initial API synchronization is intentionally initiated after mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function refreshAlerts() {
    const response = await fetch(`${API}/api/quality-alerts`);
    if (response.ok) setAlertSummary((await response.json()) as QualityAlertSummary);
  }

  function mergeRun(run: GraphRun) {
    setRuns((current) => [
      run,
      ...current.filter(
        (item) =>
          item.thread_id !== run.thread_id &&
          item.state.vehicle_id !== run.state.vehicle_id,
      ),
    ]);
  }

  function chooseUpload(file: File | null) {
    if (uploadedEvidence) URL.revokeObjectURL(uploadedEvidence.previewUrl);
    if (!file) {
      setUploadedEvidence(null);
      return;
    }
    setUploadedEvidence({
      file,
      previewUrl: URL.createObjectURL(file),
      vehicleId: `UPLOAD-${Date.now().toString().slice(-6)}`,
      vehicleModel: 'unknown_model',
      cameraId: 'CAM-FNS-FRONT',
      zoneName: 'unknown_zone',
    });
    setActiveRun(null);
    setLiveEvents([]);
  }

  async function clearHistory() {
    if (
      !window.confirm(
        t(
          'Delete all Agent traces and pending QC checkpoints?',
          'Xóa toàn bộ dấu vết Agent và các checkpoint QC đang chờ?',
        ),
      )
    )
      return;
    try {
      const response = await fetch(`${API}/agent/runs`, { method: 'DELETE' });
      if (!response.ok) throw new Error('Delete failed');
      const result = (await response.json()) as { deleted: number };
      setRuns([]);
      setAlertSummary((current) =>
        current ? { ...current, analyzed_inspections: 0, alerts: [] } : current,
      );
      setActiveRun(null);
      setLiveEvents([]);
      setNotice(
        t(
          `${result.deleted} Agent records deleted.`,
          `Đã xóa ${result.deleted} bản ghi Agent.`,
        ),
      );
    } catch {
      setNotice(
        t('Could not delete Agent history.', 'Không thể xóa lịch sử Agent.'),
      );
    }
  }

  async function createDefectCode(payload: DefectCodeInput) {
    const response = await fetch(`${API}/api/qc/defect-codes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `Request failed (${response.status})`);
    }
    const created = (await response.json()) as DefectCode;
    setDefectCodes((current) => [created, ...current.filter((item) => item.defect_code !== created.defect_code)]);
  }

  async function revealNode(
    node: string,
    detail: string,
    phase: LiveEvent['phase'] = 'completed',
  ) {
    const id = Date.now() + Math.random();
    setLiveEvents((current) => [
      ...current,
      { id, node, status: 'RUNNING', detail, phase: 'running' },
    ]);
    await wait(520);
    setLiveEvents((current) =>
      current.map((event) =>
        event.id === id
          ? {
              ...event,
              status: phase === 'waiting' ? 'WAITING' : 'COMPLETED',
              phase,
            }
          : event,
      ),
    );
  }

  async function startInspection() {
    if (!uploadedEvidence || running) return;
    setRunning(true);
    setActiveRun(null);
    setLiveEvents([]);
    setNotice(
      t(
        'Agent is extracting and processing the primary camera frame…',
        'Agent đang cắt và xử lý frame từ camera chính…',
      ),
    );
    try {
      const form = new FormData();
      const modelFile = await modelFrameFromFile(uploadedEvidence.file);
      form.append('file', modelFile);
      form.append('vehicle_id', uploadedEvidence.vehicleId);
      form.append('vehicle_model', uploadedEvidence.vehicleModel);
      form.append('camera_id', uploadedEvidence.cameraId);
      form.append('zone_name', uploadedEvidence.zoneName);
      const response = await fetch(`${API}/inspections/from-image`, {
        method: 'POST',
        body: form,
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Request failed (${response.status})`);
      }
      const result = (await response.json()) as GraphRun;
      for (const trace of result.state.execution_trace || []) {
        await revealNode(trace.node, trace.detail);
      }
      if (result.status === 'INTERRUPTED') {
        const suggestedCode = defectCodes.find(
          (item) => item.defect_code === result.state.classified_defect_code,
        ) || defectCodes.find((item) => item.defect_type === result.state.defect_type);
        if (suggestedCode) {
          setQcForm((current) => ({
            ...current,
            defectCode: suggestedCode.defect_code,
            severity: result.state.severity || suggestedCode.default_severity,
          }));
        }
        await revealNode(
          'human_review',
          result.state.reason || t('QC input required.', 'Cần QC xác nhận.'),
          'waiting',
        );
      }
      setActiveRun(result);
      mergeRun(result);
      const statusResponse = await fetch(`${API}/agent/status`);
      if (statusResponse.ok) setAgentStatus((await statusResponse.json()) as AgentStatus);
      await refreshAlerts();
      setNotice(
        result.status === 'INTERRUPTED'
          ? t('Model analysis completed; QC review is required.', 'Model đã phân tích xong; cần QC xác nhận.')
          : t('Model-backed inspection completed.', 'Kiểm tra bằng model đã hoàn tất.'),
      );
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : t('Inspection failed.', 'Inspection thất bại.'),
      );
    } finally {
      setRunning(false);
    }
  }

  async function resumeInspection(action: 'APPROVE' | 'REJECT') {
    if (!activeRun || running) return;
    setRunning(true);
    try {
      const oldTraceLength = activeRun.state.execution_trace?.length || 0;
      setLiveEvents((current) =>
        current.map((event) =>
          event.node === 'human_review' && event.phase === 'waiting'
            ? { ...event, phase: 'running', status: 'RUNNING' }
            : event,
        ),
      );
      const response = await fetch(
        `${API}/inspections/${activeRun.thread_id}/resume`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action,
            reviewer: qcForm.reviewer,
            reason: humanReason,
            defect_code: qcForm.defectCode || undefined,
            severity: qcForm.severity,
            disposition: action === 'REJECT' ? 'REINSPECT' : qcForm.disposition,
            location: qcForm.location,
            length_mm: qcForm.lengthMm ? Number(qcForm.lengthMm) : undefined,
            notes: qcForm.notes,
          }),
        },
      );
      if (!response.ok)
        throw new Error((await response.json()).detail || 'Resume failed');
      const result = (await response.json()) as GraphRun;
      setLiveEvents((current) =>
        current.map((event) =>
          event.node === 'human_review' && event.phase === 'running'
            ? {
                ...event,
                phase: 'completed',
                status: 'COMPLETED',
                detail: `QC selected ${action}.`,
              }
            : event,
        ),
      );
      const newTrace = (result.state.execution_trace || []).slice(
        oldTraceLength + 1,
      );
      for (const trace of newTrace) await revealNode(trace.node, trace.detail);
      setActiveRun(result);
      mergeRun(result);
      if (result.state.qc_decision_record) {
        setQcDecisions((current) => [
          result.state.qc_decision_record as QCDecisionRecord,
          ...current.filter(
            (item) => item.decision_id !== result.state.qc_decision_record?.decision_id,
          ),
        ]);
      }
      await refreshAlerts();
      setNotice(
        t(
          'QC decision applied; the same thread completed.',
          'Đã áp dụng quyết định QC; cùng thread đã chạy đến hoàn tất.',
        ),
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Resume failed');
    } finally {
      setRunning(false);
    }
  }

  function openRun(run: GraphRun) {
    if (uploadedEvidence) URL.revokeObjectURL(uploadedEvidence.previewUrl);
    setUploadedEvidence(null);
    setActiveRun(run);
    const events: LiveEvent[] = (run.state.execution_trace || []).map(
      (trace, index) => ({ ...trace, id: index, phase: 'completed' }),
    );
    if (run.status === 'INTERRUPTED')
      events.push({
        id: events.length,
        node: 'human_review',
        status: 'WAITING',
        detail: run.state.reason || 'QC input required',
        phase: 'waiting',
      });
    setLiveEvents(events);
    setView('inspect');
  }

  const pageTitle = NAV.find((item) => item.id === view);
  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span>VQ</span>
          <div>
            <b>Visual QC</b>
            <small>FNS · LINE HA</small>
          </div>
        </div>
        <div className="station">
          <i />
          <div>
            <small>{t('STATION STATUS', 'TRẠNG THÁI TRẠM')}</small>
            <b>{t('Ready for inspection', 'Sẵn sàng kiểm tra')}</b>
          </div>
        </div>
        <nav aria-label={t('Primary navigation', 'Điều hướng chính')}>
          <small>{t('PRIMARY WORKFLOW', 'QUY TRÌNH CHÍNH')}</small>
          {NAV.map((item) => (
            <button
              key={item.id}
              className={view === item.id ? 'nav-link active' : 'nav-link'}
              onClick={() => setView(item.id)}
            >
              <i>{item.icon}</i>
              <span>
                <b>{t(item.en, item.vi)}</b>
                <small>{t(item.hintEn, item.hintVi)}</small>
              </span>
              {item.id === 'queue' && waitingRuns.length > 0 && (
                <em>{waitingRuns.length}</em>
              )}
              {item.id === 'alerts' && (alertSummary?.alerts.length || 0) > 0 && (
                <em className="danger-badge">{alertSummary?.alerts.length}</em>
              )}
            </button>
          ))}
        </nav>
        <div className="runtime-stack">
          <div className="notice" role="status" aria-live="polite">
            <span>●</span>
            {notice}
          </div>
          <footer>
            <span>LG</span>
            <div>
              <b>LangGraph runtime</b>
              <small>{graph?.checkpointer || 'Connecting…'}</small>
            </div>
          </footer>
          <div className={`agent-access-status ${agentStatus?.reasoning.llm_accessed ? 'connected' : 'fallback'}`}>
            <i />
            <div>
              <b>{agentStatus?.reasoning.llm_accessed ? 'GROQ LLM CONNECTED' : agentStatus?.reasoning.requested_provider === 'groq' ? 'GROQ NOT ACCESSED' : 'RULE-BASED AGENT'}</b>
              <small>{agentStatus?.reasoning.last_call_status || 'CONNECTING'}</small>
            </div>
          </div>
        </div>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div>
            <small>FNS / QUALITY GATE / SHIFT A</small>
            <h1>{pageTitle ? t(pageTitle.en, pageTitle.vi) : 'Visual QC'}</h1>
          </div>
          <div className="top-actions">
            <span className={`backend-state ${backendOnline ? '' : 'offline'}`}>
              <i />
              {backendOnline ? 'API ONLINE' : 'API OFFLINE'}
            </span>
            <div className="lang-switch">
              <button
                className={lang === 'vi' ? 'active' : ''}
                onClick={() => setLang('vi')}
              >
                VIE
              </button>
              <button
                className={lang === 'en' ? 'active' : ''}
                onClick={() => setLang('en')}
              >
                ENG
              </button>
            </div>
          </div>
        </header>
        <div className={`content content-${view}`}>
          {(alertSummary?.alerts.length || 0) > 0 && view !== 'alerts' && (
            <button className="global-quality-alert" onClick={() => setView('alerts')}>
              <span>!</span>
              <div>
                <b>
                  {t(
                    'Agent detected a repeated-defect trend',
                    'Agent phát hiện xu hướng lỗi lặp lại',
                  )}
                </b>
                <small>
                  {t(
                    `${alertSummary?.alerts.length} alert(s) require upstream process verification.`,
                    `${alertSummary?.alerts.length} cảnh báo yêu cầu QC kiểm tra công đoạn phía trước.`,
                  )}
                </small>
              </div>
              <i>{t('Open alerts →', 'Mở cảnh báo →')}</i>
            </button>
          )}
          {view === 'overview' && (
            <Overview
              runs={displayRuns}
              passCount={passCount}
              holdCount={holdCount}
              waitingCount={waitingRuns.length}
              onStart={() => setView('inspect')}
              onOpen={openRun}
              t={t}
              lang={lang}
            />
          )}
          {view === 'inspect' && (
            <InspectionStudio
              run={activeRun}
              events={liveEvents}
              running={running}
              onStart={startInspection}
              onResume={resumeInspection}
              humanReason={humanReason}
              setHumanReason={setHumanReason}
              defectCodes={defectCodes}
              qcForm={qcForm}
              setQcForm={setQcForm}
              uploadedEvidence={uploadedEvidence}
              onUpload={chooseUpload}
              onUpdateUpload={(value) => setUploadedEvidence((current) => current ? { ...current, ...value } : current)}
              t={t}
              lang={lang}
            />
          )}
          {view === 'queue' && (
            <RunList
              title={t('QC decisions waiting', 'Các quyết định đang chờ QC')}
              subtitle={t(
                'Only interrupted LangGraph threads appear here.',
                'Chỉ các thread LangGraph đang tạm dừng mới xuất hiện tại đây.',
              )}
              runs={waitingRuns}
              empty={t(
                'No case is waiting for QC review.',
                'Không có case nào đang chờ QC duyệt.',
              )}
              onOpen={openRun}
              t={t}
              lang={lang}
            />
          )}
          {view === 'alerts' && (
            <QualityAlertsPage summary={alertSummary} t={t} lang={lang} />
          )}
          {view === 'catalog' && (
            <DefectRegistry
              codes={defectCodes}
              decisions={qcDecisions}
              onCreate={createDefectCode}
              t={t}
            />
          )}
          {view === 'history' && (
            <RunList
              title={t(
                'Latest LangGraph inspections',
                'Kết quả LangGraph mới nhất',
              )}
              subtitle={t(
                'Only the latest trace for each configured vehicle is shown.',
                'Mỗi xe cấu hình chỉ hiển thị dấu vết kiểm tra mới nhất.',
              )}
              runs={displayRuns}
              empty={t(
                'No LangGraph inspection has been run.',
                'Chưa có inspection LangGraph nào.',
              )}
              onOpen={openRun}
              onClear={clearHistory}
              variant="history"
              t={t}
              lang={lang}
            />
          )}
        </div>
      </section>
    </main>
  );
}

function Overview({
  runs,
  passCount,
  holdCount,
  waitingCount,
  onStart,
  onOpen,
  t,
  lang,
}: {
  runs: GraphRun[];
  passCount: number;
  holdCount: number;
  waitingCount: number;
  onStart: () => void;
  onOpen: (run: GraphRun) => void;
  t: (en: string, vi: string) => string;
  lang: Lang;
}) {
  return (
    <>
      <section className="hero">
        <div className="project-hero-copy">
          <span className="kicker">FNS BODY QUALITY · AI-ASSISTED INSPECTION</span>
          <h2>{t(
            'Visual QC Agent for explainable vehicle-body inspection.',
            'Visual QC Agent cho kiểm tra thân vỏ xe minh bạch và có kiểm soát.',
          )}</h2>
          <p>{t(
            'An Agent-first baseline connecting local computer vision, controlled QC policy, LangGraph orchestration, exception-only human review, and a complete audit trail at the FNS station.',
            'Baseline Agent-first kết nối Computer Vision chạy local, policy QC kiểm soát, điều phối LangGraph, QC chỉ xử lý ngoại lệ và lưu đầy đủ dấu vết tại trạm FNS.',
          )}</p>
          <div className="hero-badges">
            <span><i /> best.pt · segmentation</span>
            <span><i /> LangGraph · stateful</span>
            <span><i /> HITL · accountable</span>
          </div>
          <button onClick={onStart}>{t('Start an Agent inspection', 'Bắt đầu kiểm tra bằng Agent')} <b>→</b></button>
        </div>
        <aside className="hero-system-card">
          <header>
            <div><i /><span>{t('SYSTEM READY', 'HỆ THỐNG SẴN SÀNG')}</span></div>
            <b>FNS · LINE HA</b>
          </header>
          <div className="system-flow">
            <div><span>01</span><p><small>INPUT</small><b>{t('QC image upload', 'Ảnh QC tải lên')}</b></p></div>
            <i />
            <div><span>02</span><p><small>VISION</small><b>{t('Defect segmentation', 'Phân vùng lỗi')}</b></p></div>
            <i />
            <div><span>03</span><p><small>AGENT</small><b>{t('Policy orchestration', 'Điều phối policy')}</b></p></div>
            <i />
            <div><span>04</span><p><small>CONTROL</small><b>{t('Agent release or hold', 'Agent cho đi hoặc giữ xe')}</b></p></div>
          </div>
          <footer><span>MODEL</span><b>best.pt</b><span>STORE</span><b>SQLite</b></footer>
        </aside>
        <div>
          <span className="kicker">VISUAL QC · EXPLAINABLE ORCHESTRATION</span>
          <h2>
            {t(
              'One inspection. One workflow. Every decision visible.',
              'Một inspection. Một workflow. Mọi quyết định đều nhìn thấy.',
            )}
          </h2>
          <p>
            {t(
              'The local segmentation model provides evidence; LangGraph lets the Agent classify the code, apply policy, and route the vehicle automatically.',
              'Model segmentation cung cấp bằng chứng; LangGraph giúp Agent tự phân mã, áp dụng policy và điều phối xe.',
            )}
          </p>
          <button onClick={onStart}>
            {t('Start an Agent inspection', 'Bắt đầu kiểm tra bằng Agent')}{' '}
            <b>→</b>
          </button>
        </div>
        <div className="hero-orbit">
          <div className="orbit-core">
            <small>FNS</small>
            <b>QC</b>
          </div>
          <span className="orbit-node n1">CV</span>
          <span className="orbit-node n2">RULE</span>
          <span className="orbit-node n3">HITL</span>
          <span className="orbit-node n4">AUDIT</span>
        </div>
      </section>
      <section className="project-grid">
        <article className="card project-card">
          <header><div><small>{t('PROJECT PURPOSE', 'MỤC TIÊU DỰ ÁN')}</small><h3>{t('A safer and faster FNS quality gate', 'Cổng chất lượng FNS an toàn và nhanh hơn')}</h3></div></header>
          <div className="project-copy">
            <p>{t(
              'The Agent detects and classifies known body defects, applies a consistent controlled policy, and sends only new or unmapped exceptions to QC.',
              'Agent phát hiện và phân loại lỗi thân vỏ đã biết, áp dụng policy kiểm soát nhất quán và chỉ chuyển lỗi mới hoặc chưa ánh xạ cho QC.',
            )}</p>
            <div>
              <span><b>01</b>{t('Detect dents and scratches', 'Phát hiện móp và xước')}</span>
              <span><b>02</b>{t('Classify the controlled QC code', 'Tự phân loại mã lỗi QC')}</span>
              <span><b>03</b>{t('Route cases by QC policy', 'Điều phối theo QC policy')}</span>
              <span><b>04</b>{t('Preserve an audit trail', 'Lưu toàn bộ dấu vết audit')}</span>
            </div>
          </div>
        </article>
        <article className="card scope-card">
          <header><div><small>{t('MVP SCOPE', 'PHẠM VI MVP')}</small><h3>{t('What is running now', 'Những thành phần đang vận hành')}</h3></div></header>
          <div className="scope-list">
            <div><span>CV</span><p><b>Local YOLO segmentation</b><small>best.pt · bbox · mask · confidence</small></p><em>{t('ACTIVE', 'ĐANG CHẠY')}</em></div>
            <div><span>LG</span><p><b>LangGraph workflow</b><small>conditional route · verify loop · HITL</small></p><em>{t('ACTIVE', 'ĐANG CHẠY')}</em></div>
            <div><span>DB</span><p><b>SQLite audit repository</b><small>state · decision · trace · evidence</small></p><em>{t('ACTIVE', 'ĐANG CHẠY')}</em></div>
          </div>
        </article>
      </section>
      <section className="metrics">
        <Metric
          label={t('Vehicles inspected', 'Xe đã kiểm tra')}
          value={runs.length}
          tone="blue"
          note={t('latest result per vehicle', 'kết quả mới nhất mỗi xe')}
        />
        <Metric
          label="PASS"
          value={passCount}
          tone="green"
          note={t('released by policy', 'được policy cho đi tiếp')}
        />
        <Metric
          label={t('Controlled hold', 'Giữ xe kiểm soát')}
          value={holdCount}
          tone="red"
          note={t('repair or reinspection', 'sửa chữa hoặc kiểm tra lại')}
        />
        <Metric
          label={t('Waiting for QC', 'Đang chờ QC')}
          value={waitingCount}
          tone="amber"
          note={t('paused checkpoints', 'checkpoint đang tạm dừng')}
        />
      </section>
      <section className="overview-grid">
        <article className="card">
          <header>
            <div>
              <small>
                {t('SINGLE SOURCE OF TRUTH', 'MỘT NGUỒN DỮ LIỆU DUY NHẤT')}
              </small>
              <h3>{t('Agent operating chain', 'Chuỗi vận hành Agent')}</h3>
            </div>
          </header>
          <div className="operating-chain">
            <span>
              <b>01</b> YOLO segmentation
            </span>
            <i>→</i>
            <span>
              <b>02</b> LangGraph state
            </span>
            <i>→</i>
            <span>
              <b>03</b> QC decision
            </span>
            <i>→</i>
            <span>
              <b>04</b> SQLite audit
            </span>
          </div>
        </article>
      </section>
      <RecentRuns
        runs={runs.slice(0, 5)}
        onOpen={onOpen}
        t={t}
        lang={lang}
      />
    </>
  );
}

function InspectionStudio({
  run,
  events,
  running,
  onStart,
  onResume,
  humanReason,
  setHumanReason,
  defectCodes,
  qcForm,
  setQcForm,
  uploadedEvidence,
  onUpload,
  onUpdateUpload,
  t,
  lang,
}: {
  run: GraphRun | null;
  events: LiveEvent[];
  running: boolean;
  onStart: () => void;
  onResume: (action: 'APPROVE' | 'REJECT') => void;
  humanReason: string;
  setHumanReason: (value: string) => void;
  defectCodes: DefectCode[];
  qcForm: QCFormState;
  setQcForm: (value: QCFormState | ((current: QCFormState) => QCFormState)) => void;
  uploadedEvidence: UploadedEvidence | null;
  onUpload: (file: File | null) => void;
  onUpdateUpload: (value: Partial<UploadedEvidence>) => void;
  t: (en: string, vi: string) => string;
  lang: Lang;
}) {
  const bbox = run?.state.bbox || null;
  const imageWidth = run?.state.image_width || 640;
  const imageHeight = run?.state.image_height || 640;
  const maskPolygon = run?.state.segmentation_result?.points
    ?.map(([x, y]) => `${(x / imageWidth) * 100}% ${(y / imageHeight) * 100}%`)
    .join(', ');
  const guide = Boolean(run);
  const policy = run?.state.policy_decision;
  const suggestedCode = run?.state.classified_defect_code || run?.state.suggested_defect_codes?.[0]?.defect_code;
  const selectedDefectCode = defectCodes.find(
    (item) => item.defect_code === qcForm.defectCode,
  );
  const qcRecordComplete = Boolean(
    qcForm.defectCode &&
    qcForm.reviewer.trim() &&
    qcForm.location.trim() &&
    humanReason.trim().length >= 3 &&
    (!selectedDefectCode?.measurement_required || Number(qcForm.lengthMm) > 0),
  );
  const completedNodes = events.filter((event) => event.phase === 'completed').length;
  // Seven nodes exist in the graph, but conditional routes execute only the
  // nodes required by the selected path. A completed route is therefore 100%.
  const graphProgress = run?.status === 'COMPLETED'
    ? 100
    : run?.status === 'INTERRUPTED'
      ? 85
      : Math.min(90, completedNodes * 15);
  const evidenceImage = (run?.state.image_url ? `${API}${run.state.image_url}` : '') ||
    uploadedEvidence?.previewUrl || '';
  const primaryIsVideo = !run && uploadedEvidence?.file.type.startsWith('video/');
  const evidenceVehicle = uploadedEvidence?.vehicleId || run?.state.vehicle_id || '—';
  const evidenceModel = uploadedEvidence || run ? 'Web upload' : '—';
  const evidenceCamera = uploadedEvidence?.cameraId || run?.state.camera_id || '—';
  return (
    <>
      <section className="studio-head">
        <div>
          <span className="kicker">LIVE AGENT INSPECTION</span>
          <h2>
            {t(
              'Connect the primary camera and follow its frame through every Agent node.',
              'Kết nối camera chính và theo dõi frame đi qua từng node của Agent.',
            )}
          </h2>
          <p>
            {t(
              'The primary video is converted to one inspection frame before best.pt inference. Supporting cameras will be enabled in a later phase.',
              'Video camera chính được cắt thành một frame kiểm tra trước khi đưa vào best.pt. Các camera hỗ trợ sẽ được triển khai ở giai đoạn sau.',
            )}
          </p>
        </div>
        <button
          className="run-button"
          disabled={!uploadedEvidence || running}
          onClick={onStart}
        >
          <span>{running ? '···' : '▶'}</span>
          <div>
            <small>
              {running
                ? t('AGENT RUNNING', 'AGENT ĐANG CHẠY')
                : t('PRIMARY ACTION', 'THAO TÁC CHÍNH')}
            </small>
            <b>
              {running
                ? t('Processing nodes…', 'Đang xử lý từng node…')
                : t('Start inspection', 'Bắt đầu kiểm tra')}
            </b>
          </div>
        </button>
      </section>
      <section className={`upload-panel ${uploadedEvidence ? 'ready' : ''}`}>
        <label className="upload-drop">
          <input
            type="file"
            accept="image/jpeg,image/png,video/mp4,video/webm"
            disabled={running}
            onChange={(event) => onUpload(event.target.files?.[0] || null)}
          />
          <span>↑</span>
          <div>
            <small>{t('REAL MODEL INPUT', 'ĐẦU VÀO MODEL THẬT')}</small>
            <b>{uploadedEvidence?.file.name || t('Upload the front video or an inspection frame', 'Tải video phía trước hoặc một frame kiểm tra')}</b>
            <em>{t('For video, the workstation extracts the middle frame and sends only that image to best.pt.', 'Với video, workstation cắt frame ở giữa và chỉ gửi ảnh đó tới best.pt.')}</em>
          </div>
        </label>
        {uploadedEvidence && (
          <div className="upload-fields">
            <label>
              <small>VEHICLE ID</small>
              <input value={uploadedEvidence.vehicleId} onChange={(event) => onUpdateUpload({ vehicleId: event.target.value })} />
            </label>
            <label>
              <small>{t('VEHICLE MODEL', 'MODEL XE')}</small>
              <input value={uploadedEvidence.vehicleModel} onChange={(event) => onUpdateUpload({ vehicleModel: event.target.value })} />
            </label>
            <label>
              <small>CAMERA ID</small>
              <input value={uploadedEvidence.cameraId} onChange={(event) => onUpdateUpload({ cameraId: event.target.value })} />
            </label>
            <label>
              <small>ZONE NAME</small>
              <input value={uploadedEvidence.zoneName} onChange={(event) => onUpdateUpload({ zoneName: event.target.value })} />
            </label>
            <button onClick={() => onUpload(null)} disabled={running}>×</button>
          </div>
        )}
      </section>
      <section className="process-rail" aria-label={t('Inspection progress', 'Tiến trình kiểm tra')}>
        <div className={uploadedEvidence ? 'process-step complete' : 'process-step active'}>
          <span>01</span>
          <div><small>INPUT</small><b>{t('Primary evidence', 'Evidence camera chính')}</b></div>
        </div>
        <i />
        <div className={events.some((event) => event.node === 'detect_defect') ? 'process-step complete' : running ? 'process-step active' : 'process-step'}>
          <span>02</span>
          <div><small>VISION</small><b>best.pt · YOLO</b></div>
        </div>
        <i />
        <div className={run ? 'process-step complete' : events.length ? 'process-step active' : 'process-step'}>
          <span>03</span>
          <div><small>ORCHESTRATE</small><b>LangGraph</b></div>
        </div>
        <i />
        <div className={run ? 'process-step complete' : 'process-step'}>
          <span>04</span>
          <div><small>OUTCOME</small><b>{t('QC decision', 'Quyết định QC')}</b></div>
        </div>
      </section>
      <section className="studio-grid">
        <article className="camera-card card">
          <header>
            <div>
              <small>01 · {t('INSPECTION EVIDENCE', 'BẰNG CHỨNG KIỂM TRA')}</small>
              <h3>
                {evidenceVehicle} · {evidenceModel}
              </h3>
            </div>
            <span className="live-tag">
              <i /> {t('PRIMARY CAMERA', 'CAMERA CHÍNH')}
            </span>
          </header>
          {evidenceImage && (
            <>
              <div className="multiview-wall">
                <div className="camera-view primary-camera">
                  {/* Blob URLs and FastAPI evidence URLs are intentionally rendered directly. */}
                  {primaryIsVideo ? (
                    <video src={evidenceImage} autoPlay muted loop playsInline controls />
                  ) : (
                    <img src={evidenceImage} alt={uploadedEvidence?.file.name || 'Inspection evidence'} />
                  )}
                  <div className="camera-hud">
                    <span><i /> {t('CAMERA FRONT · PRIMARY', 'CAMERA TRƯỚC · CHÍNH')}</span>
                    <b>{evidenceCamera}</b>
                  </div>
                  <div className="camera-reticle" aria-hidden="true" />
                  {maskPolygon && (
                    <div
                      className="segmentation-mask"
                      style={{ clipPath: `polygon(${maskPolygon})` }}
                      aria-label={t('Model segmentation mask', 'Mask segmentation của model')}
                    />
                  )}
                  {bbox && (
                    <div
                      className="detection-box"
                      style={{
                        left: `${(bbox.x1 / imageWidth) * 100}%`,
                        top: `${(bbox.y1 / imageHeight) * 100}%`,
                        width: `${((bbox.x2 - bbox.x1) / imageWidth) * 100}%`,
                        height: `${((bbox.y2 - bbox.y1) / imageHeight) * 100}%`,
                      }}
                    >
                      <span>{pretty(run?.state.defect_type)} · {percent(run?.state.confidence)}</span>
                    </div>
                  )}
                  <div className="scan-line" />
                </div>
              </div>
              <div className="evidence-grid">
                <Data
                  label={t('Camera', 'Camera')}
                  value={evidenceCamera}
                />
                <Data
                  label={t('Inspection zone', 'Vùng kiểm tra')}
                  value={pretty(run?.state.zone_name || uploadedEvidence?.zoneName || 'unknown_zone')}
                />
                <Data
                  label={t('Input evidence', 'Evidence đầu vào')}
                  value={uploadedEvidence
                    ? t('The primary frame is sent to YOLO and then evaluated by the Agent workflow.', 'Frame camera chính được gửi tới YOLO, sau đó được workflow Agent đánh giá.')
                    : t('Stored upload evidence from the completed inspection.', 'Evidence upload đã lưu từ phiên kiểm tra.')}
                  wide
                />
                <Data
                  label={t('Model runtime', 'Model thực thi')}
                  value={run?.state.model_name
                    ? `${run.state.model_name} · ${run.state.inference_ms?.toFixed(0) || '—'} ms`
                    : t('Waiting for inference', 'Chờ model inference')}
                  wide
                />
                {run && (
                  <Data
                    label={t('Model output', 'Kết quả model')}
                    value={`${run.state.detections?.length || 0} detection · ${run.state.model_task || 'segment'} · ${run.state.model_version || '—'}`}
                    wide
                  />
                )}
                {run?.state.visual_measurements && (
                  <Data
                    label={t('Visual extent and position', 'Kích thước ảnh và vị trí lỗi')}
                    value={t(
                      `${run.state.visual_measurements.width_px.toFixed(0)} × ${run.state.visual_measurements.height_px.toFixed(0)} px · ${(run.state.visual_measurements.image_area_ratio * 100).toFixed(1)}% image · ${pretty(run.state.visual_measurements.relative_position)}${run.state.visual_measurements.estimated_width_mm ? ` · pilot estimate ${run.state.visual_measurements.estimated_width_mm.toFixed(1)} × ${run.state.visual_measurements.estimated_height_mm?.toFixed(1)} mm` : ' · millimetres require calibration'}`,
                      `${run.state.visual_measurements.width_px.toFixed(0)} × ${run.state.visual_measurements.height_px.toFixed(0)} px · ${(run.state.visual_measurements.image_area_ratio * 100).toFixed(1)}% diện tích ảnh · vị trí ${pretty(run.state.visual_measurements.relative_position)}${run.state.visual_measurements.estimated_width_mm ? ` · ước lượng pilot ${run.state.visual_measurements.estimated_width_mm.toFixed(1)} × ${run.state.visual_measurements.estimated_height_mm?.toFixed(1)} mm` : ' · số đo mm cần calibration'}`,
                    )}
                    wide
                  />
                )}
              </div>
            </>
          )}
        </article>
        <article className="decision-card card">
          <header>
            <div>
              <small>02 · {t('QUALITY DISPOSITION', 'KẾT QUẢ & ĐIỀU PHỐI')}</small>
              <h3>{t('QC operational decision', 'Quyết định vận hành QC')}</h3>
            </div>
            {running ? (
              <span className="status-pill agent-running-pill">
                {t('AGENT RUNNING', 'AGENT ĐANG CHẠY')}
              </span>
            ) : <StatusPill run={run || undefined} t={t} />}
          </header>
          {running ? (
            <section className="decision-live-trace" aria-live="polite">
              <header>
                <div>
                  <small>LANGGRAPH · LIVE EXECUTION</small>
                  <b>{t('Analyzing evidence and applying QC policy', 'Đang phân tích evidence và áp dụng QC policy')}</b>
                </div>
                <div className="trace-progress">
                  <span>{run?.thread_id ? `#${run.thread_id.slice(0, 8)}` : t('IN PROGRESS', 'ĐANG XỬ LÝ')}</span>
                  <strong>{graphProgress}%</strong>
                </div>
              </header>
              <div className="trace-meter"><i style={{ width: `${graphProgress}%` }} /></div>
              <NodeTimeline events={events} running={running} t={t} lang={lang} />
            </section>
          ) : run ? (
            <>
              <div className={`outcome ${outcomeTone(run)}`}>
                <small>{t('OPERATIONAL ACTION', 'HÀNH ĐỘNG VẬN HÀNH')}</small>
                <strong>{actionLabel(run.state, lang)}</strong>
                <AgentReasoning state={run.state} lang={lang} t={t} />
              </div>
              <div className="decision-facts">
                <Data
                  label={t('Confirmed QC code', 'Mã lỗi đã xác định')}
                  value={`${suggestedCode || t('New defect', 'Lỗi mới')} · ${defectLabel(run.state, lang)}`}
                />
                <Data
                  label={t('Pilot measurement', 'Kích thước pilot')}
                  value={run.state.visual_measurements?.estimated_length_mm
                    ? `${run.state.visual_measurements.estimated_length_mm.toFixed(1)} mm · ${run.state.visual_measurements.estimated_width_mm?.toFixed(1)} × ${run.state.visual_measurements.estimated_height_mm?.toFixed(1)} mm`
                    : t('QC measurement required', 'Cần QC đo xác nhận')}
                />
                <Data
                  label={t('Destination', 'Điểm điều phối')}
                  value={finalRouteLabel(run, lang)}
                />
                <Data
                  label={t('Test drive', 'Quyền test drive')}
                  value={run.state.allow_test_drive ? t('ALLOWED', 'CHO PHÉP') : t('BLOCKED', 'TẠM KHÓA')}
                />
              </div>
              {run.state.similar_defect_warning && (
                <div className="classification-note warning">
                  <b>{t('Repeated defect warning', 'Cảnh báo lỗi tương tự')}</b>
                  <span>{t('Multiple similar regions were detected. The Agent classified this as a defect cluster.', 'Phát hiện nhiều vùng lỗi tương tự. Agent đã phân loại đây là lỗi theo cụm.')}</span>
                </div>
              )}
              {guide && (
                <>
                  <details className="decision-rationale policy-disclosure">
                    <summary>
                      <span>DOC</span>
                      <div>
                        <small>{t('POLICY & AUDIT DETAILS', 'HỒ SƠ POLICY & AUDIT')}</small>
                        <b>{policy ? `${policy.policy_id} · revision ${policy.policy_revision}` : `Thread #${run.thread_id.slice(0, 8)}`}</b>
                      </div>
                      <div className="policy-summary-meta">
                        <i>{policy?.document_review?.matched_document_count || 0} {t('controlled documents', 'tài liệu kiểm soát')}</i>
                        <strong>
                          <span className="policy-open-label">{t('View dossier', 'Xem hồ sơ')}</span>
                          <span className="policy-close-label">{t('Close dossier', 'Đóng hồ sơ')}</span>
                        </strong>
                      </div>
                    </summary>
                    {policy?.document_review ? (
                      <div className="policy-dossier compact">
                        <div className="policy-query-bar">
                          <small>{t('LOOKUP CONTEXT', 'NGỮ CẢNH TRA CỨU')}</small>
                          <div>{Object.entries(policy.document_review.query).map(([key, value]) => (
                            <span className={value.startsWith('unknown') ? 'unknown' : ''} key={key}>
                              <b>{pretty(key)}</b>{pretty(value)}
                            </span>
                          ))}</div>
                        </div>
                        {!!policy.document_review.warnings.length && (
                          <div className="document-warnings">
                            <small>{t('DOCUMENT WARNING', 'CẢNH BÁO TÀI LIỆU')}</small>
                            {policy.document_review.warnings.map((warning, index) => (
                              <p className={warning.severity.toLowerCase()} key={`${warning.code}-${index}`}>
                                <b>{pretty(warning.code)}</b><span>{policyWarningLabel(warning.code, warning.message, lang)}</span>
                              </p>
                            ))}
                          </div>
                        )}
                        <div className="evidence-matrix">
                          <small>{t('EVIDENCE STATUS', 'TRẠNG THÁI EVIDENCE')} · {policy.document_review.missing_data.length} {t('missing', 'còn thiếu')}</small>
                          <div>{policy.document_review.evidence_comparison.map((item) => (
                            <span className={item.available ? 'available' : 'missing'} key={item.evidence}>
                              <i>{item.available ? '✓' : '!'}</i>{pretty(item.evidence)}
                            </span>
                          ))}</div>
                        </div>
                        <div className="approved-checklist">
                          <small>{t('APPROVED CHECKLIST', 'CHECKLIST ĐÃ PHÊ DUYỆT')} · {pretty(policy.document_review.checklist_status)}</small>
                          <ol>
                            {(policy.document_review.approved_checklist.length
                              ? policy.document_review.approved_checklist
                              : policy.document_review.proposed_checklist).map((step) => <li key={step}>{policyStepLabel(step, lang)}</li>)}
                          </ol>
                        </div>
                        <details className="policy-details">
                          <summary>
                            {t('View policy conditions and citations', 'Xem điều kiện policy và trích dẫn')}
                            <span>{policy.document_review.extracted_conditions.length} {t('conditions', 'điều kiện')} · {policy.document_review.citations.length} {t('documents', 'tài liệu')}</span>
                          </summary>
                          <div className="policy-detail-content">
                            <div className="policy-conditions">
                              <small>{t('EXTRACTED CONDITIONS', 'ĐIỀU KIỆN TRÍCH XUẤT')}</small>
                              <ul>{policy.document_review.extracted_conditions.map((condition) => <li key={condition}>{condition}</li>)}</ul>
                            </div>
                            <div className="document-citations">
                              <small>{t('DOCUMENT CITATIONS', 'TRÍCH DẪN TÀI LIỆU')}</small>
                              {policy.document_review.citations.length ? policy.document_review.citations.map((reference) => (
                                <a key={reference.id} href={reference.url.startsWith('/') ? `${API}${reference.url}` : reference.url} target="_blank" rel="noreferrer">
                                  <b>{reference.id}</b><span>{reference.title}</span>
                                  <em>Rev. {reference.revision} · {reference.section} · {t('Effective', 'Hiệu lực')}: {reference.effective_date || t('unconfirmed', 'chưa xác nhận')}</em>
                                </a>
                              )) : <p>{t('No context-matched controlled document was found.', 'Không tìm thấy tài liệu kiểm soát phù hợp với ngữ cảnh.')}</p>}
                            </div>
                          </div>
                        </details>
                      </div>
                    ) : <p className="policy-dossier-empty">{t('Policy document review has not run.', 'Chưa thực hiện tra cứu tài liệu policy.')}</p>}
                  </details>
                </>
              )}
              {run.status === 'INTERRUPTED' && (
                <div className="hitl-box">
                  <span>!</span>
                  <div>
                    <small>{t('HUMAN REVIEW CHECKPOINT', 'CHECKPOINT KIỂM DUYỆT')}</small>
                    <b>{t('New defect requires QC classification', 'Lỗi mới cần QC phân loại')}</b>
                    <p>
                      {t(
                        'The Agent only sends model errors or unmapped defect classes to QC. Classify this new exception before resuming the workflow.',
                        'Agent chỉ chuyển model error hoặc loại lỗi chưa có trong danh mục cho QC. Hãy phân loại ngoại lệ mới trước khi tiếp tục workflow.',
                      )}
                    </p>
                    <div className="qc-record-form">
                      <label>
                        <span>{t('DEFECT CODE', 'MÃ LỖI')}</span>
                        <select
                          value={qcForm.defectCode}
                          onChange={(event) => {
                            const selected = defectCodes.find(
                              (item) => item.defect_code === event.target.value,
                            );
                            setQcForm((current) => ({
                              ...current,
                              defectCode: event.target.value,
                              severity: selected?.default_severity || current.severity,
                            }));
                          }}
                          aria-label={t('Defect code', 'Mã lỗi')}
                        >
                          <option value="">{t('Select a controlled code', 'Chọn mã lỗi kiểm soát')}</option>
                          {defectCodes.map((item) => (
                            <option value={item.defect_code} key={item.defect_code}>
                              {item.defect_code} · {item.display_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>{t('DEFECT TYPE', 'LOẠI LỖI')}</span>
                        <input
                          value={selectedDefectCode?.defect_type || ''}
                          readOnly
                          placeholder={t('Defined by defect code', 'Tự động theo mã lỗi')}
                        />
                      </label>
                      <label>
                        <span>{t('SEVERITY', 'MỨC ĐỘ')}</span>
                        <select
                          value={qcForm.severity}
                          onChange={(event) => setQcForm((current) => ({ ...current, severity: event.target.value }))}
                        >
                          {['A', 'B', 'C', 'UNASSESSED'].map((severity) => (
                            <option value={severity} key={severity}>{severity}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>{t('DISPOSITION', 'ĐIỀU PHỐI')}</span>
                        <select
                          value={qcForm.disposition}
                          onChange={(event) => setQcForm((current) => ({
                            ...current,
                            disposition: event.target.value as QCFormState['disposition'],
                          }))}
                        >
                          <option value="HOLD">HOLD</option>
                          <option value="REWORK">REWORK</option>
                          <option value="REINSPECT">REINSPECT</option>
                          <option value="PASS">PASS</option>
                        </select>
                      </label>
                      <label>
                        <span>{t('DEFECT LOCATION', 'VỊ TRÍ LỖI')}</span>
                        <input
                          value={qcForm.location}
                          onChange={(event) => setQcForm((current) => ({ ...current, location: event.target.value }))}
                          placeholder={t('Example: left door, lower edge', 'Ví dụ: cửa trái, mép dưới')}
                        />
                      </label>
                      <label>
                        <span>
                          {t('DEFECT LENGTH (MM)', 'CHIỀU DÀI LỖI (MM)')}
                          {selectedDefectCode?.measurement_required ? ' *' : ''}
                        </span>
                        <input
                          type="number"
                          min="0"
                          step="0.1"
                          value={qcForm.lengthMm}
                          onChange={(event) => setQcForm((current) => ({ ...current, lengthMm: event.target.value }))}
                          placeholder={selectedDefectCode?.measurement_required ? t('Required QC measurement', 'Bắt buộc QC đo') : t('Optional', 'Không bắt buộc')}
                        />
                      </label>
                      <label className="wide">
                        <span>{t('QC REVIEWER', 'NGƯỜI XÁC NHẬN QC')}</span>
                        <input
                          value={qcForm.reviewer}
                          onChange={(event) => setQcForm((current) => ({ ...current, reviewer: event.target.value }))}
                          placeholder="qc-inspector-01"
                        />
                      </label>
                    </div>
                    <label>
                      <span>{t('QC REVIEW NOTE', 'GHI NHẬN CỦA QC')}</span>
                      <textarea
                        value={humanReason}
                        onChange={(event) => setHumanReason(event.target.value)}
                        aria-label={t('QC reason', 'Lý do QC')}
                        placeholder={t('Describe the visual evidence supporting your decision…', 'Mô tả evidence quan sát được để làm cơ sở quyết định…')}
                      />
                    </label>
                    <div className="hitl-actions">
                      <button
                        disabled={running || !qcRecordComplete}
                        onClick={() => onResume('REJECT')}
                      >
                        <small>{t('MODEL RESULT INCORRECT', 'KẾT QUẢ MODEL KHÔNG ĐÚNG')}</small>
                        {t('Reject finding', 'Không xác nhận lỗi')}
                      </button>
                      <button
                        className="primary"
                        disabled={running || !qcRecordComplete}
                        onClick={() => onResume('APPROVE')}
                      >
                        <small>{t('DEFECT OBSERVED', 'ĐÃ QUAN SÁT THẤY LỖI')}</small>
                        {t('Confirm defect', 'Xác nhận lỗi')}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="decision-empty">
              <span>◇</span>
              <b>{t('Waiting for inspection', 'Đang chờ kiểm tra')}</b>
              <p>
                {t(
                  'Connect the primary camera, then start the inspection.',
                  'Kết nối camera chính rồi bắt đầu kiểm tra.',
                )}
              </p>
            </div>
          )}
        </article>
      </section>
    </>
  );
}

function NodeTimeline({
  events,
  running,
  t,
  lang,
}: {
  events: LiveEvent[];
  running: boolean;
  t: (en: string, vi: string) => string;
  lang: Lang;
}) {
  if (!events.length)
    return (
      <div className="timeline-empty">
        <div className="pulse-ring" />
        <b>{t('Graph ready', 'Graph sẵn sàng')}</b>
        <p>
          {t(
            'Seven nodes are waiting for image evidence.',
            'Bảy node đang chờ evidence hình ảnh.',
          )}
        </p>
      </div>
    );
  return (
    <div className="node-timeline">
      {events.map((event, index) => (
        <div key={event.id} className={`node-row ${event.phase}`}>
          <div className="node-mark">
            {event.phase === 'completed'
              ? '✓'
              : event.phase === 'waiting'
                ? '!'
                : ''}
          </div>
          <div>
            <small>{String(index + 1).padStart(2, '0')} · LANGGRAPH NODE</small>
            <b>{local(NODE_COPY[event.node], lang, pretty(event.node))}</b>
            <p>{translateDetail(event, lang)}</p>
          </div>
          <em>
            {event.phase === 'running'
              ? t('RUNNING', 'ĐANG CHẠY')
              : event.phase === 'waiting'
                ? t('WAITING QC', 'CHỜ QC')
                : t('DONE', 'XONG')}
          </em>
        </div>
      ))}
      {running && (
        <div className="stream-indicator">
          <i />
          <span>
            {t('Receiving state updates…', 'Đang nhận cập nhật state…')}
          </span>
        </div>
      )}
    </div>
  );
}

function DefectRegistry({
  codes,
  decisions,
  onCreate,
  t,
}: {
  codes: DefectCode[];
  decisions: QCDecisionRecord[];
  onCreate: (payload: DefectCodeInput) => Promise<void>;
  t: (en: string, vi: string) => string;
}) {
  const [draft, setDraft] = useState<DefectCodeInput>({
    defect_code: '',
    defect_type: 'scratch',
    cv_label: 'scratch',
    defect_family: 'SURFACE_SCRATCH',
    display_name: '',
    description: '',
    classification_rule: 'QC confirmation required',
    default_severity: 'C',
    measurement_required: true,
    active: true,
  });
  const [saving, setSaving] = useState(false);
  const [formMessage, setFormMessage] = useState('');

  async function submitCode() {
    setSaving(true);
    setFormMessage('');
    try {
      await onCreate(draft);
      setFormMessage(t('Defect code saved.', 'Đã lưu mã lỗi.'));
      setDraft((current) => ({ ...current, defect_code: '', display_name: '', description: '' }));
    } catch (error) {
      setFormMessage(error instanceof Error ? error.message : t('Could not save code.', 'Không thể lưu mã lỗi.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="defect-registry-page">
      <div className="registry-intro card">
        <div>
          <small>QC MASTER DATA · CV LABEL MAPPING</small>
          <h2>{t('Controlled defect registry', 'Sổ mã lỗi kiểm soát')}</h2>
          <p>
            {t(
              'The Agent maps the Computer Vision label to this controlled catalog. Length and relative location support policy evaluation.',
              'Agent ánh xạ label Computer Vision với danh mục kiểm soát này. Chiều dài và vị trí tương đối hỗ trợ đánh giá policy.',
            )}
          </p>
        </div>
        <span>{codes.length} {t('active codes', 'mã đang dùng')}</span>
      </div>

      <article className="registry-card registry-create-card card">
        <header>
          <div>
            <small>01 · QC MASTER DATA INPUT</small>
            <h3>{t('Add a controlled defect code', 'Thêm mã lỗi QC thủ công')}</h3>
          </div>
          <span>{t('Saved to database', 'Lưu vào database')}</span>
        </header>
        <div className="registry-form">
          <label><small>{t('Defect code', 'Mã lỗi')}</small><input value={draft.defect_code} placeholder="SCRATCH02" onChange={(event) => setDraft({ ...draft, defect_code: event.target.value.toUpperCase() })} /></label>
          <label><small>CV LABEL</small><select value={draft.cv_label} onChange={(event) => setDraft({ ...draft, cv_label: event.target.value, defect_type: event.target.value })}><option value="scratch">scratch</option><option value="dent">dent</option></select></label>
          <label><small>{t('Defect family', 'Nhóm mã lỗi')}</small><input value={draft.defect_family} placeholder="SURFACE_SCRATCH" onChange={(event) => setDraft({ ...draft, defect_family: event.target.value.toUpperCase() })} /></label>
          <label><small>{t('Display name', 'Tên hiển thị')}</small><input value={draft.display_name} placeholder={t('Fine surface scratch', 'Vết xước mảnh')} onChange={(event) => setDraft({ ...draft, display_name: event.target.value })} /></label>
          <label><small>SEVERITY</small><select value={draft.default_severity} onChange={(event) => setDraft({ ...draft, default_severity: event.target.value })}><option>A</option><option>B</option><option>C</option><option>UNASSESSED</option></select></label>
          <label className="registry-description"><small>{t('Description / criteria', 'Mô tả / tiêu chí')}</small><input value={draft.description} placeholder={t('Describe the controlled defect subtype', 'Mô tả cụ thể phân loại lỗi')} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
          <label className="registry-description"><small>{t('Agent classification rule', 'Rule phân loại cho Agent')}</small><input value={draft.classification_rule} placeholder="estimated_width_mm <= 50" onChange={(event) => setDraft({ ...draft, classification_rule: event.target.value })} /></label>
          <label className="registry-check"><input type="checkbox" checked={draft.measurement_required} onChange={(event) => setDraft({ ...draft, measurement_required: event.target.checked })} /><span>{t('QC physical measurement required', 'QC bắt buộc xác nhận kích thước thực')}</span></label>
          <button className="registry-save" disabled={saving || draft.defect_code.length < 3 || draft.display_name.length < 2} onClick={submitCode}>{saving ? t('Saving…', 'Đang lưu…') : t('Save defect code', 'Lưu mã lỗi')}</button>
          {formMessage && <p className="registry-form-message">{formMessage}</p>}
        </div>
      </article>

      <article className="registry-card card">
        <header>
          <div>
            <small>02 · DEFECT CATALOG</small>
            <h3>{t('CV label → controlled code', 'Label CV → mã lỗi chuẩn')}</h3>
          </div>
        </header>
        <div className="registry-table-wrap">
          <table className="registry-table">
            <thead>
              <tr>
                <th>{t('Code', 'Mã lỗi')}</th>
                <th>CV label</th>
                <th>{t('Defect type', 'Loại lỗi')}</th>
                <th>{t('Family', 'Nhóm')}</th>
                <th>Severity</th>
                <th>{t('Length', 'Chiều dài')}</th>
                <th>{t('Description', 'Mô tả')}</th>
              </tr>
            </thead>
            <tbody>
              {codes.map((item) => (
                <tr key={item.defect_code}>
                  <td><b>{item.defect_code}</b></td>
                  <td><code>{item.cv_label}</code></td>
                  <td>{pretty(item.defect_type)}</td>
                  <td><code>{item.defect_family}</code></td>
                  <td><span className="severity-chip">{item.default_severity}</span></td>
                  <td>{item.measurement_required ? t('QC measurement required', 'QC bắt buộc đo') : t('Optional', 'Không bắt buộc')}</td>
                  <td>{item.description}<small>{item.classification_rule}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>

      <article className="registry-card card">
        <header>
          <div>
            <small>03 · QC CONFIRMED RECORDS</small>
            <h3>{t('Measured defects and decisions', 'Lỗi đã đo và quyết định QC')}</h3>
          </div>
          <span>{decisions.length} {t('records', 'bản ghi')}</span>
        </header>
        <div className="registry-table-wrap">
          <table className="registry-table decision-registry-table">
            <thead>
              <tr>
                <th>{t('Vehicle / inspection', 'Xe / inspection')}</th>
                <th>{t('Code / type', 'Mã / loại lỗi')}</th>
                <th>{t('Defect location', 'Vị trí lỗi')}</th>
                <th>{t('Length', 'Chiều dài')}</th>
                <th>{t('QC decision', 'Quyết định QC')}</th>
                <th>{t('Reviewer', 'Người xác nhận')}</th>
              </tr>
            </thead>
            <tbody>
              {decisions.length ? decisions.map((item) => (
                <tr key={item.decision_id}>
                  <td><b>{item.vehicle_id}</b><small>{item.inspection_id.slice(0, 12)}</small></td>
                  <td><b>{item.defect_code}</b><small>{pretty(item.defect_type)} · {item.severity}</small></td>
                  <td><b>{item.location}</b></td>
                  <td>{item.length_mm == null ? '—' : `${item.length_mm.toFixed(1)} mm`}</td>
                  <td><span className={`disposition-chip disposition-${item.disposition.toLowerCase()}`}>{item.disposition}</span><small>{item.action}</small></td>
                  <td><b>{item.reviewer}</b><small>{new Date(item.created_at).toLocaleString()}</small></td>
                </tr>
              )) : (
                <tr><td colSpan={6} className="registry-empty">{t('No QC-confirmed record is available yet.', 'Chưa có bản ghi nào được QC xác nhận.')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}

function QualityAlertsPage({
  summary,
  t,
  lang,
}: {
  summary: QualityAlertSummary | null;
  t: (en: string, vi: string) => string;
  lang: Lang;
}) {
  const criticalCount =
    summary?.alerts.filter((item) => item.severity === 'CRITICAL').length || 0;
  const affectedVehicles =
    summary?.alerts.reduce((total, item) => total + item.affected_vehicle_count, 0) || 0;
  return (
    <div className="alert-page">
      <section className="alert-hero">
        <div>
          <span className="kicker">QUALITY EARLY WARNING</span>
          <h2>{t('Repeated defect alerts', 'Cảnh báo lỗi lặp lại')}</h2>
          <p>
            {t(
              'The Agent groups repeated defects and tells QC what needs attention and what to check next.',
              'Agent gom các lỗi lặp lại, chỉ rõ vấn đề cần chú ý và hành động QC cần thực hiện tiếp theo.',
            )}
          </p>
        </div>
        <a
          className="report-download"
          href={`${API}/api/quality-alerts/report.docx`}
        >
          <span>DOCX</span>
          <div>
            <b>{t('Download QC report', 'Tải báo cáo QC')}</b>
            <small>{t('Alert evidence and actions', 'Bằng chứng và hành động')}</small>
          </div>
          <i>↓</i>
        </a>
      </section>

      <section className="alert-metrics">
        <article>
          <small>{t('INSPECTIONS MONITORED', 'LƯỢT ĐÃ GIÁM SÁT')}</small>
          <strong>{summary?.analyzed_inspections || 0}</strong>
          <p>{t('latest inspection window', 'trong cửa sổ gần nhất')}</p>
        </article>
        <article className="warning">
          <small>{t('OPEN ALERTS', 'CẢNH BÁO CẦN XỬ LÝ')}</small>
          <strong>{summary?.alerts.length || 0}</strong>
          <p>{t('require QC action', 'cần QC hành động')}</p>
        </article>
        <article className="critical">
          <small>{t('CRITICAL', 'NGHIÊM TRỌNG')}</small>
          <strong>{criticalCount}</strong>
          <p>{t('immediate escalation', 'cần chuyển xử lý ngay')}</p>
        </article>
        <article>
          <small>{t('AFFECTED VEHICLES', 'XE BỊ ẢNH HƯỞNG')}</small>
          <strong>{affectedVehicles}</strong>
          <p>{t('across active alerts', 'trong cảnh báo hiện tại')}</p>
        </article>
      </section>

      {summary?.alerts.length ? (
        <section className="alert-stack">
          {summary.alerts.map((alert) => {
            const checks =
              lang === 'vi' ? alert.upstream_checks_vi : alert.upstream_checks_en;
            const knownZone = alert.zone_name && !alert.zone_name.startsWith('unknown');
            const defectCodes = Array.from(new Set([
              ...(alert.related_defect_codes || []),
              ...(alert.occurrences || []).map((item) => item.classified_defect_code),
            ].filter(Boolean)));
            const visualEvidence = (alert.occurrences || [])
              .filter((item, index, items) =>
                Boolean(item.image_url) &&
                items.findIndex((candidate) => candidate.image_url === item.image_url) === index,
              )
              .slice(0, 4);
            return (
              <article
                className={`trend-alert ${alert.severity.toLowerCase()}`}
                key={alert.id}
              >
                <header>
                  <div className="alert-symbol">!</div>
                  <div>
                    <span>
                      {alert.severity} · {alert.affected_vehicle_count}{' '}
                      {t('VEHICLES', 'XE')}
                    </span>
                    <h3>{pretty(alert.defect_type)}{knownZone ? ` · ${pretty(alert.zone_name)}` : ''}</h3>
                    <p>
                      {t(
                        `${alert.occurrence_count} repeated detections require an upstream process check.`,
                        `Phát hiện ${alert.occurrence_count} lần lặp lại; cần kiểm tra công đoạn trước.`,
                      )}
                    </p>
                  </div>
                  <span className="alert-open">
                    {t('ACTION REQUIRED', 'CẦN XỬ LÝ')}
                  </span>
                </header>
                <div className="alert-evidence-grid">
                  <div><small>{t('REPEATED', 'SỐ LẦN LẶP')}</small><b>{alert.occurrence_count}</b></div>
                  <div><small>{t('AFFECTED VEHICLES', 'XE ẢNH HƯỞNG')}</small><b>{alert.affected_vehicle_count}</b></div>
                  <div><small>{t('CAMERA', 'CAMERA PHÁT HIỆN')}</small><b>{alert.camera_id}</b></div>
                  <div><small>{t('LAST SEEN', 'PHÁT HIỆN GẦN NHẤT')}</small><b>{new Date(alert.last_seen).toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-US')}</b></div>
                </div>
                <section className="alert-visual-evidence">
                  <header>
                    <div>
                      <small>{t('VISUAL EVIDENCE', 'BẰNG CHỨNG TRỰC QUAN')}</small>
                      <h4>{t('Repeated defect samples', 'Ảnh lỗi ghi nhận lặp lại')}</h4>
                    </div>
                    <div className="alert-code-list" aria-label={t('Related defect codes', 'Mã lỗi liên quan')}>
                      {defectCodes.length ? defectCodes.map((code) => (
                        <span key={code}>{code}</span>
                      )) : <span>{t('Code pending', 'Chưa có mã lỗi')}</span>}
                    </div>
                  </header>
                  {visualEvidence.length ? (
                    <div className="alert-image-strip">
                      {visualEvidence.map((item) => {
                        const imageSource = item.image_url.startsWith('http')
                          ? item.image_url
                          : `${API}${item.image_url}`;
                        return (
                          <figure key={`${item.inspection_id}-${item.image_url}`}>
                            <img src={imageSource} alt={`${pretty(item.defect_type)} · ${item.vehicle_id}`} />
                            <figcaption>
                              <b>{item.classified_defect_code || pretty(item.defect_type)}</b>
                              <span>{item.vehicle_id}</span>
                              <small>{new Date(item.inspected_at).toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-US')}</small>
                            </figcaption>
                          </figure>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="alert-no-image">
                      {t('No retained image is available for this alert.', 'Chưa có ảnh được lưu cho cảnh báo này.')}
                    </p>
                  )}
                </section>
                <div className="upstream-plan">
                  <div>
                    <small>{t('ACTION NOW', 'HÀNH ĐỘNG NGAY')}</small>
                    <h4>
                      {t(
                        'Check the suspected upstream source',
                        'Kiểm tra nguồn phát sinh nghi ngờ',
                      )}
                    </h4>
                    <ol>
                      {checks.slice(0, 3).map((check, index) => (
                        <li key={check}>
                          <span>{index + 1}</span>
                          <p>{check}</p>
                        </li>
                      ))}
                    </ol>
                  </div>
                  <aside>
                    <small>
                      {t('AGENT CONCLUSION', 'KẾT LUẬN CỦA AGENT')}
                    </small>
                    <b>
                      {lang === 'vi'
                        ? alert.recommendation_vi
                        : alert.recommendation_en}
                    </b>
                    <p><strong>{t('Suspected source:', 'Nguồn nghi ngờ:')}</strong> {alert.predicted_root_cause}</p>
                    <p><strong>{t('Responsible area:', 'Bộ phận xử lý:')}</strong> {alert.upstream_target_shop}</p>
                    <p className="alert-close-rule">
                      <strong>{t('Close when:', 'Đóng cảnh báo khi:')}</strong>{' '}
                      {t(
                        'QC records the upstream check and confirms the repeated defect has stopped.',
                        'QC ghi nhận kết quả kiểm tra và xác nhận lỗi không còn lặp lại.',
                      )}
                    </p>
                  </aside>
                </div>
              </article>
            );
          })}
        </section>
      ) : (
        <section className="alert-empty card">
          <span>✓</span>
          <h3>{t('No repeated-defect alert', 'Chưa có cảnh báo lỗi lặp')}</h3>
          <p>
            {t(
              'No defect group has crossed the configured threshold in the current window.',
              'Chưa có nhóm lỗi nào vượt ngưỡng cấu hình trong cửa sổ hiện tại.',
            )}
          </p>
        </section>
      )}
    </div>
  );
}

function RunList({
  title,
  subtitle,
  runs,
  empty,
  onOpen,
  onClear,
  variant = 'queue',
  t,
  lang,
}: {
  title: string;
  subtitle: string;
  runs: GraphRun[];
  empty: string;
  onOpen: (run: GraphRun) => void;
  onClear?: () => void;
  variant?: 'queue' | 'history';
  t: (en: string, vi: string) => string;
  lang: Lang;
}) {
  return (
    <>
      <section className="list-head">
        <div>
          <span className="kicker">LANGGRAPH RECORDS</span>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        <div className="list-tools">
          {onClear && runs.length > 0 && (
            <button className="clear-history" onClick={onClear}>
              <span>×</span>
              {t('Clear history', 'Xóa lịch sử')}
            </button>
          )}
          <strong>{runs.length.toString().padStart(2, '0')}</strong>
        </div>
      </section>
      <section className={`run-list card ${variant === 'history' ? 'history-records' : ''}`}>
        {runs.length ? (
          runs.map((run) => {
            const imageSource = run.state.image_url
              ? (run.state.image_url.startsWith('http') ? run.state.image_url : `${API}${run.state.image_url}`)
              : '';
            const measurement = run.state.visual_measurements;
            const estimatedLength = measurement?.estimated_length_mm;
            const recordTime = run.state.qc_decision_record?.created_at;
            if (variant === 'history') {
              return (
                <button className="history-record" key={run.thread_id} onClick={() => onOpen(run)}>
                  <div className="history-thumb">
                    {imageSource ? (
                      <img src={imageSource} alt={`${run.state.vehicle_id} inspection evidence`} />
                    ) : (
                      <span>QC</span>
                    )}
                  </div>
                  <div className="history-main">
                    <div className="history-title">
                      <div>
                        <small>{t('VEHICLE / INSPECTION', 'XE / PHIÊN KIỂM TRA')}</small>
                        <b>{run.state.vehicle_id}</b>
                        <em>#{run.state.inspection_id?.slice(0, 8)} · Thread #{run.thread_id.slice(0, 8)}</em>
                      </div>
                      <StatusPill run={run} t={t} />
                    </div>
                    <div className="history-facts">
                      <div>
                        <small>{t('DEFECT', 'LỖI PHÁT HIỆN')}</small>
                        <b>{run.state.defect_detected ? pretty(run.state.defect_type) : t('No defect', 'Không có lỗi')}</b>
                        <em>{run.state.classified_defect_code || t('No defect code', 'Chưa có mã lỗi')}</em>
                      </div>
                      <div>
                        <small>{t('MODEL EVIDENCE', 'BẰNG CHỨNG MODEL')}</small>
                        <b>{percent(run.state.confidence)}</b>
                        <em>{run.state.camera_id}</em>
                      </div>
                      <div>
                        <small>{t('SIZE / LOCATION', 'KÍCH THƯỚC / VỊ TRÍ')}</small>
                        <b>{estimatedLength != null ? `${estimatedLength.toFixed(1)} mm` : t('Not available', 'Chưa có số đo')}</b>
                        <em>{measurement?.relative_position ? pretty(measurement.relative_position) : pretty(run.state.zone_name)}</em>
                      </div>
                      <div className="history-decision">
                        <small>{t('FINAL ACTION', 'HÀNH ĐỘNG CUỐI')}</small>
                        <b>{actionLabel(run.state, lang)}</b>
                        <em>{recordTime ? new Date(recordTime).toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-US') : pretty(run.state.final_status)}</em>
                      </div>
                    </div>
                  </div>
                  <i>→</i>
                </button>
              );
            }
            return (
              <button className="queue-record" key={run.thread_id} onClick={() => onOpen(run)}>
                <div className="queue-thumb">
                  {imageSource ? (
                    <img src={imageSource} alt={`${run.state.vehicle_id} QC evidence`} />
                  ) : (
                    <span>QC</span>
                  )}
                </div>
                <div className="queue-main">
                  <div className="queue-title">
                    <div>
                      <small>{t('QC CHECKPOINT', 'CHECKPOINT KIỂM DUYỆT')}</small>
                      <b>{run.state.vehicle_id}</b>
                      <em>Thread #{run.thread_id.slice(0, 8)}</em>
                    </div>
                    <StatusPill run={run} t={t} />
                  </div>
                  <div className="queue-facts">
                    <div>
                      <small>{t('DEFECT / CODE', 'LỖI / MÃ LỖI')}</small>
                      <b>{run.state.defect_detected ? pretty(run.state.defect_type) : t('Unknown defect', 'Lỗi chưa xác định')}</b>
                      <em>{run.state.classified_defect_code || t('New defect — QC classification required', 'Lỗi mới — cần QC phân loại')}</em>
                    </div>
                    <div>
                      <small>{t('MODEL EVIDENCE', 'BẰNG CHỨNG MODEL')}</small>
                      <b>{percent(run.state.confidence)}</b>
                      <em>{estimatedLength != null ? `${estimatedLength.toFixed(1)} mm` : t('Size unavailable', 'Chưa có kích thước')}</em>
                    </div>
                    <div>
                      <small>{t('LOCATION', 'VỊ TRÍ')}</small>
                      <b>{measurement?.relative_position ? pretty(measurement.relative_position) : pretty(run.state.zone_name)}</b>
                      <em>{run.state.camera_id}</em>
                    </div>
                  </div>
                  <div className="queue-reason">
                    <div>
                      <small>{t('WHY QC IS NEEDED', 'LÝ DO CẦN QC')}</small>
                      <p>{run.interrupt?.reason || run.state.reason || t('The Agent needs QC confirmation for a new or unsupported case.', 'Agent cần QC xác nhận trường hợp mới hoặc chưa có quy tắc xử lý.')}</p>
                    </div>
                    <span>{t('Open review', 'Mở kiểm duyệt')} →</span>
                  </div>
                </div>
              </button>
            );
          })
        ) : (
          <div className="empty-state">
            <span>◇</span>
            <b>{empty}</b>
            <p>
              {t(
                'Upload a vehicle image in Agent inspection to create the first record.',
                'Hãy tải ảnh xe trong màn hình Kiểm tra bằng Agent để tạo bản ghi đầu tiên.',
              )}
            </p>
          </div>
        )}
      </section>
    </>
  );
}

function RecentRuns({
  runs,
  onOpen,
  t,
  lang,
}: {
  runs: GraphRun[];
  onOpen: (run: GraphRun) => void;
  t: (en: string, vi: string) => string;
  lang: Lang;
}) {
  return (
    <section className="card recent">
      <header>
        <div>
          <small>{t('RECENT ACTIVITY', 'HOẠT ĐỘNG GẦN ĐÂY')}</small>
          <h3>{t('Latest Agent decisions', 'Quyết định Agent mới nhất')}</h3>
        </div>
      </header>
      {runs.length ? (
        <div>
          {runs.map((run) => (
              <button key={run.thread_id} onClick={() => onOpen(run)}>
                <span className={`decision-dot ${outcomeTone(run)}`} />
                <span>
                  <b>{run.state.vehicle_id}</b>
                  <small>{pretty(run.state.defect_type)}</small>
                </span>
                <strong>{actionLabel(run.state, lang)}</strong>
                <StatusPill run={run} t={t} />
              </button>
          ))}
        </div>
      ) : (
        <div className="empty-inline">
          {t(
            'No inspections yet — upload the first image.',
            'Chưa có inspection — hãy tải ảnh đầu tiên.',
          )}
        </div>
      )}
    </section>
  );
}

function Metric({
  label,
  value,
  tone,
  note,
}: {
  label: string;
  value: number;
  tone: string;
  note: string;
}) {
  return (
    <article className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{String(value).padStart(2, '0')}</strong>
      <small>{note}</small>
    </article>
  );
}
function Data({
  label,
  value,
  wide = false,
}: {
  label: string;
  value: string;
  wide?: boolean;
}) {
  return (
    <div className={wide ? 'data wide' : 'data'}>
      <small>{label}</small>
      <b>{value}</b>
    </div>
  );
}
function AgentReasoning({
  state,
  lang,
  t,
}: {
  state: QCState;
  lang: Lang;
  t: (en: string, vi: string) => string;
}) {
  const visual = state.visual_measurements;
  const selected = state.suggested_defect_codes?.find(
    (item) => item.defect_code === state.classified_defect_code,
  );
  const certainty = percent(
    state.defect_code_classification?.confidence ?? state.confidence,
  );
  const impactLabels: Record<string, readonly [string, string]> = {
    A: ['High impact', 'Ảnh hưởng cao'],
    B: ['Significant impact', 'Ảnh hưởng đáng chú ý'],
    C: ['Minor impact', 'Ảnh hưởng nhẹ'],
  };
  const impact = local(
    impactLabels[state.severity || ''],
    lang,
    t('Not assigned', 'Chưa phân hạng'),
  );
  const size = visual?.estimated_length_mm
    ? t(
        `${visual.estimated_length_mm.toFixed(1)} mm long, ${visual.estimated_width_mm?.toFixed(1)} × ${visual.estimated_height_mm?.toFixed(1)} mm`,
        `dài ${visual.estimated_length_mm.toFixed(1)} mm, vùng bao ${visual.estimated_width_mm?.toFixed(1)} × ${visual.estimated_height_mm?.toFixed(1)} mm`,
      )
    : t('Physical size unavailable', 'Chưa có kích thước vật lý');
  const policy = state.policy_decision;
  const steps = [
    {
      label: t('1 · Evidence', '1 · Bằng chứng'),
      value: `${defectLabel(state, lang)} · ${size} · ${pretty(state.zone_name)} / ${pretty(visual?.relative_position)}`,
    },
    {
      label: t('2 · Classification', '2 · Phân loại'),
      value: `${state.classified_defect_code || t('Unmapped', 'Chưa ánh xạ')} · ${selected?.display_name || defectLabel(state, lang)} · ${certainty} · ${state.severity || '—'} (${impact})`,
    },
    {
      label: t('3 · Applied policy', '3 · Policy áp dụng'),
      value: policy
        ? `${policy.policy_id} · rev. ${policy.policy_revision}`
        : t('No matching controlled policy', 'Chưa có policy kiểm soát phù hợp'),
    },
    {
      label: t('4 · Agent decision', '4 · Agent quyết định'),
      value: `${actionLabel(state, lang)} · ${state.allow_test_drive ? t('test drive allowed', 'cho phép test drive') : t('test drive blocked', 'khóa test drive')}`,
    },
  ];
  return (
    <section className="agent-reasoning" aria-label={t('Agent reasoning', 'Lập luận của Agent')}>
      <b>{t('AGENT REASONING', 'AGENT REASONING')}</b>
      <ol>
        {steps.map((step) => (
          <li key={step.label}>
            <small>{step.label}</small>
            <span>{step.value}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
function StatusPill({
  run,
  t,
}: {
  run?: GraphRun;
  t: (en: string, vi: string) => string;
}) {
  const tone = outcomeTone(run);
  const text = !run
    ? 'READY'
    : run.status === 'INTERRUPTED'
      ? t('WAITING QC', 'CHỜ QC')
      : run.state.final_status === 'PASS'
        ? 'PASS'
        : t('CONTROLLED HOLD', 'GIỮ XE');
  return (
    <span className={`status-pill ${tone}`}>
      <i />
      {text}
    </span>
  );
}
function translateDetail(event: LiveEvent, lang: Lang) {
  if (lang === 'en') return event.detail;
  const copy: Record<string, string> = {
    prepare_input: 'Đã kiểm tra ảnh, camera và dữ liệu nhận diện xe.',
    detect_defect:
      'best.pt đã trả kết quả segmentation, confidence và vùng bbox.',
    assess_result: event.detail.includes('VERIFY')
      ? 'Confidence nằm trong vùng mơ hồ; chuyển sang xác minh lần hai.'
      : event.detail.includes('HITL')
        ? 'Kết quả chưa đủ an toàn để tự động quyết định; chuyển QC.'
        : event.detail.includes('PASS')
          ? 'Không xác nhận lỗi; đủ điều kiện đi thẳng đến bước lưu.'
          : 'Kết quả đạt ngưỡng xác nhận tự động theo rule.',
    verify_defect: `Đã hoàn thành lượt xác minh bổ sung. ${event.detail}`,
    human_review:
      event.phase === 'waiting'
        ? 'Graph đã lưu checkpoint và đang chờ QC xác nhận.'
        : 'Đã nhận quyết định của QC và tiếp tục cùng thread.',
    generate_recommendation: 'Rule QC đã tạo phương án xử lý vận hành cụ thể.',
    save_result: 'State cuối và dấu vết thực thi đã được lưu vào SQLite.',
  };
  return copy[event.node] || event.detail;
}
