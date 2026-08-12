'use client';

import { useCallback, useEffect, useState } from 'react';

type Lang = 'vi' | 'en';
type View = 'overview' | 'inspect' | 'queue' | 'alerts' | 'history';
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
  panel: string;
  material: string;
  defect_detected?: boolean;
  defect_type?: string;
  confidence?: number;
  bbox?: { x1: number; y1: number; x2: number; y2: number } | null;
  segmentation_result?: { format: string; points: number[][] } | null;
  detections?: Array<{
    class_name: string;
    raw_class_name: string;
    confidence: number;
    bbox: { x1: number; y1: number; x2: number; y2: number };
  }>;
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
  execution_trace?: TraceEvent[];
};
type GraphRun = {
  thread_id: string;
  status: 'COMPLETED' | 'INTERRUPTED';
  state: QCState;
  interrupt?: { reason?: string; allowed_actions?: string[] };
};
type GraphSpec = { nodes: string[]; checkpointer: string; mermaid: string };
type UploadedEvidence = {
  file: File;
  previewUrl: string;
  vehicleId: string;
  vehicleModel: string;
  cameraId: string;
  panel: string;
  material: string;
};
type InspectionFinding = {
  inspection_id: string;
  thread_id: string;
  vehicle_id: string;
  inspected_at: string;
  defect_type: string;
  panel: string;
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
  panels: string[];
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
  panel: string;
  camera_id: string;
  occurrence_count: number;
  affected_vehicle_count: number;
  affected_vehicle_ids: string[];
  average_confidence: number;
  maximum_confidence: number;
  first_seen: string;
  last_seen: string;
  window_hours: number;
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
  minimum_occurrences: number;
  analyzed_inspections: number;
  defect_breakdown: DefectAggregate[];
  findings: InspectionFinding[];
  alerts: QualityAlert[];
};

const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';
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
    MEASURE_PANEL_GEOMETRY: ['Measure panel geometry', 'Đo hình học panel'],
    COMPARE_WITH_APPROVED_DRAWING: ['Compare with approved drawing', 'Đối chiếu bản vẽ đã phê duyệt'],
    QC_REINSPECTION: ['Perform QC reinspection', 'QC kiểm tra lại'],
  };
  return local(labels[value], lang, pretty(value));
};
const policyWarningLabel = (code: string, fallback: string, lang: Lang) => {
  if (lang === 'en') return fallback;
  const labels: Record<string, string> = {
    POLICY_QUERY_CONTEXT_INCOMPLETE: 'Thiếu model xe, panel hoặc vật liệu để tìm đúng tài liệu.',
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
    paint_defect: ['Paint defect', 'Lỗi sơn'],
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

const verificationLabel = (state: QCState, lang: Lang) => {
  if (!state.verify_count) return lang === 'vi' ? 'Không yêu cầu xác minh' : 'Verification not required';
  const result = state.verify_result === 'CONFIRMED'
    ? (lang === 'vi' ? 'Đã xác nhận' : 'Confirmed')
    : (lang === 'vi' ? 'Chưa rõ' : 'Uncertain');
  return `${state.verify_count}/2 · ${result}`;
};

function decisionGuide(run: GraphRun, lang: Lang) {
  const code = run.state.recommendation_code || '';
  if (run.status === 'INTERRUPTED' || code === 'MANUAL_VISUAL_REINSPECTION') {
    return {
      testDrive: lang === 'vi' ? 'TẠM KHÓA' : 'BLOCKED',
      releaseGate: lang === 'vi' ? 'QC xác nhận trực tiếp và resume workflow' : 'QC confirmation and workflow resume',
      policy: lang === 'vi' ? 'Kết quả dưới ngưỡng an toàn hoặc vẫn mơ hồ sau xác minh.' : 'Result is below the safety threshold or remains uncertain after verification.',
      steps: lang === 'vi'
        ? ['Giữ xe tại trạm QC và khóa luồng release.', 'Chụp lại dưới ánh sáng kiểm soát hoặc camera bổ sung.', 'QC xác nhận loại lỗi, mức độ và vùng panel.', 'Resume đúng thread để Agent hoàn tất điều phối.']
        : ['Hold the vehicle at QC and block release.', 'Recapture under controlled light or a secondary camera.', 'Confirm defect type, severity, and panel.', 'Resume the same thread to complete routing.'],
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
      policy: lang === 'vi' ? 'Vết móp được xác nhận ở confidence cao; xe phải được cô lập để đánh giá hình học panel.' : 'High-confidence dent requires isolation and panel geometry assessment.',
      steps: lang === 'vi'
        ? ['Gắn trạng thái HOLD và khóa test drive.', 'Chuyển xe tới khu đánh giá Body Repair.', 'Đo hình học panel và đánh giá khả năng sửa chữa.', 'Thực hiện repair theo hướng dẫn đã phê duyệt.', 'QC kiểm tra lại và ghi nhận trước khi release.']
        : ['Apply HOLD and block test drive.', 'Transfer to Body Repair assessment.', 'Measure panel geometry and repairability.', 'Repair under an approved instruction.', 'QC reinspects and records acceptance before release.'],
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
  const [activeRun, setActiveRun] = useState<GraphRun | null>(null);
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [uploadedEvidence, setUploadedEvidence] = useState<UploadedEvidence | null>(null);
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
      const [graphResponse, runResponse, alertResponse] = await Promise.all([
        fetch(`${API}/agent/graph`),
        fetch(`${API}/agent/runs`),
        fetch(`${API}/api/quality-alerts`),
      ]);
      if (!graphResponse.ok || !runResponse.ok || !alertResponse.ok)
        throw new Error('Backend unavailable');
      setGraph((await graphResponse.json()) as GraphSpec);
      setRuns((await runResponse.json()) as GraphRun[]);
      setAlertSummary((await alertResponse.json()) as QualityAlertSummary);
      setNotice(
        t(
          'Workstation connected. Upload an inspection image to start.',
          'Đã kết nối workstation. Hãy tải ảnh kiểm tra để bắt đầu.',
        ),
      );
    } catch {
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
      cameraId: 'cam-web-upload',
      panel: 'unknown_panel',
      material: 'unknown_material',
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
        'Agent is processing the selected image…',
        'Agent đang xử lý ảnh đã chọn…',
      ),
    );
    try {
      const form = new FormData();
      form.append('file', uploadedEvidence.file);
      form.append('vehicle_id', uploadedEvidence.vehicleId);
      form.append('vehicle_model', uploadedEvidence.vehicleModel);
      form.append('camera_id', uploadedEvidence.cameraId);
      form.append('panel', uploadedEvidence.panel);
      form.append('material', uploadedEvidence.material);
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
        await revealNode(
          'human_review',
          result.state.reason || t('QC input required.', 'Cần QC xác nhận.'),
          'waiting',
        );
      }
      setActiveRun(result);
      mergeRun(result);
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
            reviewer: 'qc-inspector-01',
            reason: humanReason,
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
        </div>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div>
            <small>FNS / QUALITY GATE / SHIFT A</small>
            <h1>{pageTitle ? t(pageTitle.en, pageTitle.vi) : 'Visual QC'}</h1>
          </div>
          <div className="top-actions">
            <span className="backend-state">
              <i />
              API ONLINE
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
            'A baseline MVP connecting local computer vision, deterministic QC policy, LangGraph orchestration, human review, and a complete SQLite audit trail at the FNS station.',
            'Baseline MVP kết nối Computer Vision chạy local, QC policy xác định, điều phối LangGraph, kiểm duyệt của con người và dấu vết SQLite đầy đủ tại trạm FNS.',
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
            <div><span>04</span><p><small>CONTROL</small><b>{t('QC release or hold', 'QC cho đi hoặc giữ xe')}</b></p></div>
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
              'The local segmentation model analyzes each image before LangGraph performs verification and accountable QC review.',
              'Model segmentation local phân tích từng ảnh trước khi LangGraph xác minh và chuyển QC chịu trách nhiệm.',
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
              'The system helps QC operators detect visible body defects, apply a consistent decision workflow, and stop ambiguous or unsafe cases for human confirmation.',
              'Hệ thống hỗ trợ nhân viên QC phát hiện lỗi ngoại quan thân vỏ, áp dụng quy trình quyết định nhất quán và dừng các trường hợp mơ hồ hoặc không an toàn để con người xác nhận.',
            )}</p>
            <div>
              <span><b>01</b>{t('Detect dents and scratches', 'Phát hiện móp và xước')}</span>
              <span><b>02</b>{t('Verify uncertain output', 'Xác minh kết quả chưa rõ')}</span>
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
  const guide = run ? decisionGuide(run, lang) : null;
  const policy = run?.state.policy_decision;
  const completedNodes = events.filter((event) => event.phase === 'completed').length;
  // Seven nodes exist in the graph, but conditional routes execute only the
  // nodes required by the selected path. A completed route is therefore 100%.
  const graphProgress = run?.status === 'COMPLETED'
    ? 100
    : run?.status === 'INTERRUPTED'
      ? 85
      : Math.min(90, completedNodes * 15);
  const evidenceImage = uploadedEvidence?.previewUrl ||
    (run?.state.image_url ? `${API}${run.state.image_url}` : '');
  const evidenceVehicle = uploadedEvidence?.vehicleId || run?.state.vehicle_id || '—';
  const evidenceModel = uploadedEvidence || run ? 'Web upload' : '—';
  const evidenceCamera = uploadedEvidence?.cameraId || run?.state.camera_id || '—';
  const evidencePanel = uploadedEvidence?.panel || run?.state.panel || 'unknown_panel';
  return (
    <>
      <section className="studio-head">
        <div>
          <span className="kicker">LIVE AGENT INSPECTION</span>
          <h2>
            {t(
              'Upload an inspection image and watch every node execute.',
              'Tải ảnh kiểm tra và theo dõi từng node thực thi.',
            )}
          </h2>
          <p>
            {t(
              'The selected image is analyzed by best.pt; class, confidence, bounding box, and mask come from the model.',
              'Ảnh đã chọn được best.pt phân tích; class, confidence, bounding box và mask đều do model trả về.',
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
            accept="image/jpeg,image/png"
            disabled={running}
            onChange={(event) => onUpload(event.target.files?.[0] || null)}
          />
          <span>↑</span>
          <div>
            <small>{t('REAL MODEL INPUT', 'ĐẦU VÀO MODEL THẬT')}</small>
            <b>{uploadedEvidence?.file.name || t('Upload a JPEG or PNG image', 'Tải ảnh JPEG hoặc PNG')}</b>
            <em>{t('The backend will run best.pt; the browser does not provide class or confidence.', 'Backend sẽ chạy best.pt; trình duyệt không cung cấp class hay confidence.')}</em>
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
              <small>PANEL</small>
              <input value={uploadedEvidence.panel} onChange={(event) => onUpdateUpload({ panel: event.target.value })} />
            </label>
            <label>
              <small>{t('MATERIAL', 'VẬT LIỆU')}</small>
              <input value={uploadedEvidence.material} onChange={(event) => onUpdateUpload({ material: event.target.value })} />
            </label>
            <button onClick={() => onUpload(null)} disabled={running}>×</button>
          </div>
        )}
      </section>
      <section className="process-rail" aria-label={t('Inspection progress', 'Tiến trình kiểm tra')}>
        <div className={uploadedEvidence ? 'process-step complete' : 'process-step active'}>
          <span>01</span>
          <div><small>INPUT</small><b>{t('Image evidence', 'Ảnh bằng chứng')}</b></div>
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
              <i /> YOLO SEGMENT
            </span>
          </header>
          {evidenceImage && (
            <>
              <div className="camera-view">
                {/* Blob URLs and FastAPI evidence URLs are intentionally rendered directly. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={evidenceImage}
                  alt={uploadedEvidence?.file.name || 'Inspection evidence'}
                />
                <div className="camera-hud">
                  <span><i /> LIVE EVIDENCE</span>
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
                    <span>
                      {pretty(run?.state.defect_type)}{' '}
                      ·{' '}
                      {percent(
                        run?.state.confidence,
                      )}
                    </span>
                  </div>
                )}
                <div className="scan-line" />
              </div>
              <div className="evidence-grid">
                <Data
                  label={t('Camera', 'Camera')}
                  value={evidenceCamera}
                />
                <Data
                  label={t('Panel', 'Panel')}
                  value={pretty(run?.state.panel || evidencePanel)}
                />
                <Data
                  label={t('Input evidence', 'Evidence đầu vào')}
                  value={uploadedEvidence
                    ? t('Uploaded from the QC workstation for best.pt inference.', 'Ảnh được tải từ workstation để best.pt inference.')
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
                <p><b>{t('Plain-language explanation:', 'Giải thích dễ hiểu:')}</b> {localizedReason(run.state, lang)}</p>
              </div>
              <div className="decision-facts">
                <Data
                  label={t('Defect', 'Lỗi')}
                  value={defectLabel(run.state, lang)}
                />
                <Data
                  label="Confidence"
                  value={percent(run.state.confidence)}
                />
                <Data
                  label={t('Severity', 'Mức độ')}
                  value={run.state.severity || t('Not assigned', 'Chưa phân hạng')}
                />
                <Data
                  label={t('Panel / camera', 'Panel / camera')}
                  value={`${pretty(run.state.panel)} · ${run.state.camera_id}`}
                />
                <Data
                  label={t('Verification', 'Xác minh')}
                  value={verificationLabel(run.state, lang)}
                />
                <Data
                  label={t('Final route', 'Điều phối cuối')}
                  value={finalRouteLabel(run, lang)}
                />
              </div>
              {guide && (
                <>
                  <div className="safety-gates">
                    <div className="safety-gate danger">
                      <small>{t('TEST DRIVE GATE', 'QUYỀN TEST DRIVE')}</small>
                      <b>{policy?.test_drive_allowed === false ? t('BLOCKED', 'TẠM KHÓA') : guide.testDrive}</b>
                    </div>
                    <div className="safety-gate">
                      <small>{t('RELEASE CONDITION', 'ĐIỀU KIỆN RELEASE')}</small>
                      <b>{policy?.production_eligible
                        ? guide.releaseGate
                        : policy?.policy_status === 'APPROVED' && policy.approval_scope === 'DEMO_BASELINE_ONLY'
                          ? t('Demo approved; production release remains locked', 'Đã phê duyệt demo; vẫn khóa release sản xuất')
                          : t('Plant approval and QC sign-off required', 'Cần policy nhà máy phê duyệt và QC ký xác nhận')}</b>
                    </div>
                  </div>
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
                    <b>{t('QC decision required to continue', 'Cần QC xác nhận để tiếp tục')}</b>
                    <p>
                      {t(
                        'The Agent cannot finalize this case automatically. Review the image and record your conclusion before resuming the workflow.',
                        'Agent chưa đủ cơ sở tự động kết luận. Hãy đối chiếu ảnh và ghi nhận kết luận trước khi tiếp tục workflow.',
                      )}
                    </p>
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
                        disabled={running}
                        onClick={() => onResume('REJECT')}
                      >
                        <small>{t('MODEL RESULT INCORRECT', 'KẾT QUẢ MODEL KHÔNG ĐÚNG')}</small>
                        {t('Reject finding', 'Không xác nhận lỗi')}
                      </button>
                      <button
                        className="primary"
                        disabled={running}
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
                  'Upload an image and press Start inspection. The decision will appear only after its nodes execute.',
                  'Tải ảnh rồi bấm Bắt đầu kiểm tra. Quyết định chỉ xuất hiện sau khi các node thực thi.',
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
  return (
    <div className="alert-page">
      <section className="alert-hero">
        <div>
          <span className="kicker">QUALITY TREND MONITOR</span>
          <h2>{t('Repeated defect early warning', 'Cảnh báo sớm lỗi lặp lại')}</h2>
          <p>
            {t(
              'The Agent groups the latest result per vehicle by defect, panel, and camera. Three affected vehicles within 24 hours trigger an upstream process check.',
              'Agent nhóm kết quả mới nhất của mỗi xe theo loại lỗi, panel và camera. Từ 3 xe trong 24 giờ sẽ yêu cầu kiểm tra công đoạn phía trước.',
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
            <small>{t('Evidence and check plan', 'Evidence và kế hoạch kiểm tra')}</small>
          </div>
          <i>↓</i>
        </a>
      </section>

      <section className="alert-metrics">
        <article>
          <small>{t('INSPECTIONS ANALYZED', 'PHIÊN ĐÃ PHÂN TÍCH')}</small>
          <strong>{summary?.analyzed_inspections || 0}</strong>
          <p>{t('latest record per vehicle', 'bản ghi mới nhất mỗi xe')}</p>
        </article>
        <article className="warning">
          <small>{t('OPEN ALERTS', 'CẢNH BÁO MỞ')}</small>
          <strong>{summary?.alerts.length || 0}</strong>
          <p>{t('threshold ≥ 3 vehicles', 'ngưỡng ≥ 3 xe')}</p>
        </article>
        <article className="critical">
          <small>{t('CRITICAL', 'NGHIÊM TRỌNG')}</small>
          <strong>{criticalCount}</strong>
          <p>{t('five or more vehicles', 'từ 5 xe trở lên')}</p>
        </article>
        <article>
          <small>{t('MONITORING WINDOW', 'CỬA SỔ GIÁM SÁT')}</small>
          <strong>{summary?.window_hours || 24}h</strong>
          <p>{t('rolling trend window', 'cửa sổ xu hướng trượt')}</p>
        </article>
      </section>

      {!!summary?.defect_breakdown.length && (
        <section className="defect-breakdown card">
          <header>
            <div>
              <small>{t('INSPECTION HISTORY SUMMARY', 'TỔNG HỢP LỊCH SỬ KIỂM TRA')}</small>
              <h3>{t('Defects retained in the monitoring window', 'Các lỗi ghi nhận trong cửa sổ giám sát')}</h3>
            </div>
            <span>{summary.findings.length} {t('findings', 'kết quả lỗi')}</span>
          </header>
          <div className="defect-breakdown-grid">
            {summary.defect_breakdown.map((item) => (
              <article key={item.defect_type}>
                <div>
                  <span>{pretty(item.defect_type).slice(0, 2).toUpperCase()}</span>
                  <p><small>{t('DEFECT TYPE', 'LOẠI LỖI')}</small><b>{pretty(item.defect_type)}</b></p>
                </div>
                <dl>
                  <div><dt>{t('Occurrences', 'Số lần')}</dt><dd>{item.occurrence_count}</dd></div>
                  <div><dt>{t('Vehicles', 'Số xe')}</dt><dd>{item.affected_vehicle_count}</dd></div>
                  <div><dt>{t('Average', 'Trung bình')}</dt><dd>{percent(item.average_confidence)}</dd></div>
                  <div><dt>{t('Maximum', 'Cao nhất')}</dt><dd>{percent(item.maximum_confidence)}</dd></div>
                </dl>
                <p className="breakdown-scope">
                  <b>{item.panels.map(pretty).join(', ')}</b>
                  <span>{item.camera_ids.join(', ')}</span>
                </p>
              </article>
            ))}
          </div>
        </section>
      )}

      {summary?.alerts.length ? (
        <section className="alert-stack">
          {summary.alerts.map((alert) => {
            const checks =
              lang === 'vi' ? alert.upstream_checks_vi : alert.upstream_checks_en;
            const routeCounts = (alert.occurrences || []).reduce<Record<string, number>>(
              (counts, occurrence) => ({
                ...counts,
                [occurrence.final_status]: (counts[occurrence.final_status] || 0) + 1,
              }),
              {},
            );
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
                    <h3>{pretty(alert.defect_type)} · {pretty(alert.panel)}</h3>
                    <p>{lang === 'vi' ? alert.message_vi : alert.message_en}</p>
                  </div>
                  <span className="alert-open">
                    {t('UPSTREAM CHECK', 'CHECK KHÂU TRƯỚC')}
                  </span>
                </header>
                <div className="alert-evidence-grid">
                  <div><small>CAMERA</small><b>{alert.camera_id}</b></div>
                  <div><small>{t('AVERAGE CONFIDENCE', 'CONFIDENCE TRUNG BÌNH')}</small><b>{percent(alert.average_confidence)}</b></div>
                  <div><small>{t('MAX CONFIDENCE', 'CONFIDENCE CAO NHẤT')}</small><b>{percent(alert.maximum_confidence)}</b></div>
                  <div><small>{t('LAST SEEN', 'LẦN CUỐI')}</small><b>{new Date(alert.last_seen).toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-US')}</b></div>
                </div>
                <section className="trend-analysis">
                  <div className="trend-analysis-copy">
                    <div className="trend-analysis-title">
                      <span>AI</span>
                      <p>
                        <small>{t('AGENT TREND ANALYSIS', 'AGENT PHÂN TÍCH XU HƯỚNG')}</small>
                        <b>{t('Consolidated signal from inspection history', 'Tín hiệu tổng hợp từ lịch sử kiểm tra')}</b>
                      </p>
                    </div>
                    <p>
                      {alert.ai_analysis
                        ? (lang === 'vi' ? alert.ai_analysis.summary_vi : alert.ai_analysis.summary_en)
                        : (lang === 'vi' ? alert.message_vi : alert.message_en)}
                    </p>
                    {!!alert.ai_analysis?.risk_flags.length && (
                      <div className="reasoning-flags">
                        {alert.ai_analysis.risk_flags.map((flag) => <span key={flag}>{pretty(flag)}</span>)}
                      </div>
                    )}
                  </div>
                  <div className="trend-overview">
                    <small>{t('AGGREGATED INSPECTION SIGNAL', 'TỔNG QUAN CÁC LẦN KIỂM TRA')}</small>
                    <dl>
                      <div><dt>{t('Detections', 'Lần phát hiện')}</dt><dd>{alert.occurrence_count}</dd></div>
                      <div><dt>{t('Vehicles', 'Xe ảnh hưởng')}</dt><dd>{alert.affected_vehicle_count}</dd></div>
                      <div><dt>{t('Observed span', 'Khoảng ghi nhận')}</dt><dd>{new Date(alert.first_seen).toLocaleDateString(lang === 'vi' ? 'vi-VN' : 'en-US')} – {new Date(alert.last_seen).toLocaleDateString(lang === 'vi' ? 'vi-VN' : 'en-US')}</dd></div>
                    </dl>
                    <div className="route-summary">
                      <b>{t('ROUTE DISTRIBUTION', 'PHÂN BỐ ĐIỀU PHỐI')}</b>
                      <div>
                        {Object.entries(routeCounts).map(([route, count]) => (
                          <span key={route}>{pretty(route)} <strong>{count}</strong></span>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>
                <div className="upstream-plan">
                  <div>
                    <small>AGENT CHECK PLAN</small>
                    <h4>
                      {t(
                        'Required verification before release',
                        'Xác minh bắt buộc trước khi release',
                      )}
                    </h4>
                    <ol>
                      {checks.map((check, index) => (
                        <li key={check}>
                          <span>{index + 1}</span>
                          <p>{check}</p>
                        </li>
                      ))}
                    </ol>
                  </div>
                  <aside>
                    <small>
                      {t('CONTROL RECOMMENDATION', 'KHUYẾN NGHỊ KIỂM SOÁT')}
                    </small>
                    <b>
                      {lang === 'vi'
                        ? alert.recommendation_vi
                        : alert.recommendation_en}
                    </b>
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
  t,
  lang,
}: {
  title: string;
  subtitle: string;
  runs: GraphRun[];
  empty: string;
  onOpen: (run: GraphRun) => void;
  onClear?: () => void;
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
      <section className="run-list card">
        {runs.length ? (
          runs.map((run) => (
              <button key={run.thread_id} onClick={() => onOpen(run)}>
                <div className="run-vehicle">
                  <span>QC</span>
                  <div>
                    <b>{run.state.vehicle_id}</b>
                    <small>Thread #{run.thread_id.slice(0, 8)}</small>
                  </div>
                </div>
                <div>
                  <small>{t('DETECTION', 'PHÁT HIỆN')}</small>
                  <b>
                    {run.state.defect_detected
                      ? pretty(run.state.defect_type)
                      : t('No defect', 'Không có lỗi')}
                  </b>
                  <em>
                    {percent(run.state.confidence)} · {run.state.camera_id}
                  </em>
                </div>
                <div className="run-action">
                  <small>{t('ACTION', 'HÀNH ĐỘNG')}</small>
                  <b>{actionLabel(run.state, lang)}</b>
                </div>
                <StatusPill run={run} t={t} />
                <i>→</i>
              </button>
          ))
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
function localizedReason(state: QCState, lang: Lang) {
  if (state.ai_analysis)
    return lang === 'vi' ? state.ai_analysis.summary_vi : state.ai_analysis.summary_en;
  if (lang === 'en') return state.reason || 'No reason recorded.';
  const defect =
    state.defect_type === 'dent'
      ? 'Vết móp'
      : state.defect_type === 'scratch'
        ? 'Vết xước'
        : 'Kết quả';
  if (state.final_status === 'PASS')
    return 'Không phát hiện lỗi thân vỏ trong ảnh kiểm tra; xe đủ điều kiện đi tiếp.';
  if (state.human_decision?.action === 'REJECT')
    return 'QC không xác nhận kết quả tự động. Xe tiếp tục được giữ để kiểm tra ngoại quan lại.';
  if (state.recommendation_code === 'SURFACE_POLISH_AND_REINSPECT')
    return `${defect} được xác nhận ở mức ${percent(state.confidence)}. Sau đánh bóng có kiểm soát, bắt buộc kiểm tra và ghi nhận lại bề mặt.`;
  if (state.recommendation_code === 'ISOLATE_FOR_BODY_REPAIR_ASSESSMENT')
    return `${defect} được xác nhận ở mức ${percent(state.confidence)}. Xe bị khóa release cho đến khi Body Repair đánh giá hình học panel và khả năng sửa chữa.`;
  return state.reason || 'Kết quả chưa đủ rõ; cần QC xác nhận trực tiếp.';
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
