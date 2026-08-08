'use client';

import { useEffect, useState } from 'react';

type Lang = 'vi' | 'en';
type View = 'overview' | 'inspect' | 'queue' | 'history';
type TraceEvent = { node: string; status: string; detail: string };
type LiveEvent = TraceEvent & {
  id: number;
  phase: 'running' | 'completed' | 'waiting';
};
type QCState = {
  thread_id: string;
  inspection_id: string;
  vehicle_id: string;
  image_url: string;
  camera_id: string;
  panel: string;
  defect_detected?: boolean;
  defect_type?: string;
  confidence?: number;
  bbox?: { x1: number; y1: number; x2: number; y2: number } | null;
  severity?: string;
  decision?: string;
  reason?: string;
  verify_count?: number;
  verify_result?: string;
  human_required?: boolean;
  human_decision?: { action: string; reviewer: string; reason: string };
  recommendation_code?: string;
  recommendation?: string;
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
type MockCase = {
  id: string;
  image_url: string;
  filename: string;
  vehicle_id: string;
  model: string;
  defect_type: string;
  confidence: number;
  camera_id: string;
  panel: string;
  bbox: { x1: number; y1: number; x2: number; y2: number };
  severity_rank: string;
  visual_note: string;
  graph_scenario: string;
  case_title: string;
  expected_path: string;
  expected_outcome: string;
};
type StreamNode = {
  type: 'node';
  thread_id: string;
  node: string;
  update: Partial<QCState>;
};
type StreamResult = {
  type: 'result';
  thread_id: string;
  status: GraphRun['status'];
  state: QCState;
  interrupt?: GraphRun['interrupt'];
};
type StreamError = { type: 'error'; message: string };

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
  ISOLATE_FOR_BODY_REPAIR_ASSESSMENT: [
    'Hold and transfer to Body Repair',
    'Giữ xe và chuyển Bộ phận sửa chữa thân vỏ',
  ],
  MANUAL_VISUAL_REINSPECTION: [
    'Hold for a new manual inspection',
    'Giữ xe để kiểm tra ngoại quan thủ công lại',
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
  if (code === 'SURFACE_POLISH_AND_REINSPECT') {
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
  const [cases, setCases] = useState<MockCase[]>([]);
  const [runs, setRuns] = useState<GraphRun[]>([]);
  const [graph, setGraph] = useState<GraphSpec | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState('');
  const [activeRun, setActiveRun] = useState<GraphRun | null>(null);
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState('Đang kết nối workstation…');
  const [humanReason, setHumanReason] = useState(
    'Đã xác nhận trực tiếp dưới ánh sáng kiểm soát.',
  );
  const t = (en: string, vi: string) => (lang === 'vi' ? vi : en);
  const selectedCase =
    cases.find((item) => item.id === selectedCaseId) || cases[0];
  const caseVehicleIds = new Set(cases.map((item) => item.vehicle_id));
  const displayRuns = Array.from(
    new Map(
      runs
        .filter((item) => caseVehicleIds.has(item.state.vehicle_id))
        .map((item) => [item.state.vehicle_id, item]),
    ).values(),
  );
  const waitingRuns = displayRuns.filter((item) => item.status === 'INTERRUPTED');
  const completedRuns = displayRuns.filter((item) => item.status === 'COMPLETED');
  const passCount = completedRuns.filter(
    (item) => item.state.final_status === 'PASS',
  ).length;
  const holdCount = completedRuns.filter(
    (item) => item.state.final_status && item.state.final_status !== 'PASS',
  ).length;

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      const [caseResponse, graphResponse, runResponse] = await Promise.all([
        fetch(`${API}/api/simulations/cases`),
        fetch(`${API}/agent/graph`),
        fetch(`${API}/agent/runs`),
      ]);
      if (!caseResponse.ok || !graphResponse.ok || !runResponse.ok)
        throw new Error('Backend unavailable');
      const caseData = (await caseResponse.json()) as MockCase[];
      setCases(caseData);
      setSelectedCaseId((current) => current || caseData[0]?.id || '');
      setGraph((await graphResponse.json()) as GraphSpec);
      setRuns((await runResponse.json()) as GraphRun[]);
      setNotice(
        t(
          'Workstation connected. Select a vehicle example to start.',
          'Đã kết nối workstation. Chọn một xe mẫu để bắt đầu.',
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

  function chooseCase(id: string) {
    setSelectedCaseId(id);
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
    if (!selectedCase || running) return;
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
      const response = await fetch(`${API}/inspections/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vehicle_id: selectedCase.vehicle_id,
          image_url: selectedCase.image_url,
          camera_id: selectedCase.camera_id,
          panel: selectedCase.panel,
          mock_scenario: selectedCase.graph_scenario,
          mock_detection: {
            defect_detected: selectedCase.graph_scenario !== 'no_defect',
            defect_type:
              selectedCase.graph_scenario === 'no_defect'
                ? 'none'
                : selectedCase.defect_type,
            confidence: selectedCase.confidence,
            bbox:
              selectedCase.graph_scenario === 'no_defect'
                ? null
                : selectedCase.bbox,
            severity: selectedCase.severity_rank,
          },
        }),
      });
      if (!response.ok || !response.body)
        throw new Error(`Request failed (${response.status})`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let finalRun: GraphRun | null = null;
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line) as
            | StreamNode
            | StreamResult
            | StreamError;
          if (event.type === 'error') throw new Error(event.message);
          if (event.type === 'node') {
            const trace = event.update.execution_trace?.at(-1);
            await revealNode(
              event.node,
              trace?.detail || t('Node completed.', 'Node đã hoàn thành.'),
            );
          } else {
            finalRun = {
              thread_id: event.thread_id,
              status: event.status,
              state: event.state,
              interrupt: event.interrupt,
            };
          }
        }
        if (done) break;
      }
      if (!finalRun) throw new Error('Stream ended without a result');
      if (finalRun.status === 'INTERRUPTED')
        await revealNode(
          'human_review',
          finalRun.state.reason || t('QC input required.', 'Cần QC xác nhận.'),
          'waiting',
        );
      setActiveRun(finalRun);
      mergeRun(finalRun);
      setNotice(
        finalRun.status === 'INTERRUPTED'
          ? t(
              'Workflow paused safely at QC review.',
              'Workflow đã dừng an toàn tại bước QC xác nhận.',
            )
          : t(
              'Inspection completed and saved.',
              'Inspection đã hoàn tất và được lưu.',
            ),
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
    const relatedCase = cases.find(
      (item) => item.vehicle_id === run.state.vehicle_id,
    );
    if (relatedCase) setSelectedCaseId(relatedCase.id);
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
        <div className="content">
          {view === 'overview' && (
            <Overview
              runs={displayRuns}
              cases={cases}
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
              cases={cases}
              selectedCase={selectedCase}
              setSelectedCaseId={chooseCase}
              run={activeRun}
              events={liveEvents}
              running={running}
              onStart={startInspection}
              onResume={resumeInspection}
              humanReason={humanReason}
              setHumanReason={setHumanReason}
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
              cases={cases}
              empty={t(
                'No case is waiting for QC review.',
                'Không có case nào đang chờ QC duyệt.',
              )}
              onOpen={openRun}
              t={t}
              lang={lang}
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
              cases={cases}
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
  cases,
  passCount,
  holdCount,
  waitingCount,
  onStart,
  onOpen,
  t,
  lang,
}: {
  runs: GraphRun[];
  cases: MockCase[];
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
              'Image-backed mock detections move through the real LangGraph state machine, including verification loops and accountable QC review.',
              'Dữ liệu mock có ảnh đi qua state machine LangGraph thật, gồm vòng xác minh và bước QC chịu trách nhiệm.',
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
              <small>{t('AVAILABLE EVIDENCE', 'EVIDENCE SẴN CÓ')}</small>
              <h3>
                {t('Image-backed inspection examples', 'Ví dụ kiểm tra có ảnh')}
              </h3>
            </div>
            <span>{cases.length} cases</span>
          </header>
          <div className="case-strip">
            {cases.map((item) => (
              <button key={item.id} onClick={onStart}>
                <img src={`${API}${item.image_url}`} alt={item.case_title} />
                <span>
                  <b>{item.vehicle_id}</b>
                  <small>{item.case_title}</small>
                </span>
              </button>
            ))}
          </div>
        </article>
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
              <b>01</b> CV payload
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
        cases={cases}
        onOpen={onOpen}
        t={t}
        lang={lang}
      />
    </>
  );
}

function InspectionStudio({
  cases,
  selectedCase,
  setSelectedCaseId,
  run,
  events,
  running,
  onStart,
  onResume,
  humanReason,
  setHumanReason,
  t,
  lang,
}: {
  cases: MockCase[];
  selectedCase?: MockCase;
  setSelectedCaseId: (id: string) => void;
  run: GraphRun | null;
  events: LiveEvent[];
  running: boolean;
  onStart: () => void;
  onResume: (action: 'APPROVE' | 'REJECT') => void;
  humanReason: string;
  setHumanReason: (value: string) => void;
  t: (en: string, vi: string) => string;
  lang: Lang;
}) {
  const bbox =
    run?.state.bbox ||
    (selectedCase?.graph_scenario !== 'no_defect' ? selectedCase?.bbox : null);
  const guide = run ? decisionGuide(run, lang) : null;
  return (
    <>
      <section className="studio-head">
        <div>
          <span className="kicker">LIVE AGENT INSPECTION</span>
          <h2>
            {t(
              'Select a vehicle example and watch every node execute.',
              'Chọn một xe mẫu và theo dõi từng node thực thi.',
            )}
          </h2>
          <p>
            {t(
              'The mock profile is attached to the image. There is no branch selector and no separate trace engine.',
              'Demo mock đã gắn với ảnh với thông số và dữ liệu trả về của CV.',
            )}
          </p>
        </div>
        <button
          className="run-button"
          disabled={!selectedCase || running}
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
      <section
        className="case-catalog"
        aria-label={t('Mock inspection examples', 'Các ví dụ kiểm tra mock')}
      >
        {cases.map((item) => (
          <button
            key={item.id}
            className={
              selectedCase?.id === item.id ? 'case-tile selected' : 'case-tile'
            }
            onClick={() => !running && setSelectedCaseId(item.id)}
          >
            <img src={`${API}${item.image_url}`} alt={item.case_title} />
            <span>
              <b>{item.vehicle_id}</b>
              <small>{item.case_title}</small>
            </span>
            <em>
              {item.graph_scenario === 'no_defect'
                ? 'CLEAR'
                : percent(item.confidence)}
            </em>
          </button>
        ))}
      </section>
      <section className="studio-grid">
        <article className="camera-card card">
          <header>
            <div>
              <small>01 · VISUAL EVIDENCE</small>
              <h3>
                {selectedCase?.vehicle_id || '—'} · {selectedCase?.model || '—'}
              </h3>
            </div>
            <span className="live-tag">
              <i /> MOCK CAMERA
            </span>
          </header>
          {selectedCase && (
            <>
              <div className="camera-view">
                <img
                  src={`${API}${selectedCase.image_url}`}
                  alt={selectedCase.case_title}
                />
                {bbox && (
                  <div
                    className="detection-box"
                    style={{
                      left: `${(bbox.x1 / 640) * 100}%`,
                      top: `${(bbox.y1 / 640) * 100}%`,
                      width: `${((bbox.x2 - bbox.x1) / 640) * 100}%`,
                      height: `${((bbox.y2 - bbox.y1) / 640) * 100}%`,
                    }}
                  >
                    <span>
                      {pretty(
                        run?.state.defect_type || selectedCase.defect_type,
                      )}{' '}
                      ·{' '}
                      {percent(
                        run?.state.confidence ?? selectedCase.confidence,
                      )}
                    </span>
                  </div>
                )}
                <div className="scan-line" />
              </div>
              <div className="evidence-grid">
                <Data
                  label={t('Camera', 'Camera')}
                  value={selectedCase.camera_id}
                />
                <Data
                  label={t('Panel', 'Panel')}
                  value={pretty(run?.state.panel || 'body_panel')}
                />
                <Data
                  label={t('Mock observation', 'Quan sát mock')}
                  value={selectedCase.visual_note}
                  wide
                />
              </div>
            </>
          )}
        </article>
        <article className="trace-card card">
          <header>
            <div>
              <small>02 · LANGGRAPH LIVE TRACE</small>
              <h3>{t('Node execution', 'Thực thi từng node')}</h3>
            </div>
            <span>
              {run?.thread_id ? `#${run.thread_id.slice(0, 8)}` : 'READY'}
            </span>
          </header>
          <NodeTimeline events={events} running={running} t={t} lang={lang} />
        </article>
        <article className="decision-card card">
          <header>
            <div>
              <small>03 · OPERATIONAL OUTCOME</small>
              <h3>{t('Agent decision', 'Quyết định của Agent')}</h3>
            </div>
            <StatusPill run={run || undefined} t={t} />
          </header>
          {run ? (
            <>
              <div className={`outcome ${outcomeTone(run)}`}>
                <small>{t('MANDATORY ACTION', 'HÀNH ĐỘNG BẮT BUỘC')}</small>
                <strong>{actionLabel(run.state, lang)}</strong>
                <p>{localizedReason(run.state, lang)}</p>
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
                      <b>{guide.testDrive}</b>
                    </div>
                    <div className="safety-gate">
                      <small>{t('RELEASE CONDITION', 'ĐIỀU KIỆN RELEASE')}</small>
                      <b>{guide.releaseGate}</b>
                    </div>
                  </div>
                  <section className="decision-method">
                    <div className="section-title">
                      <span>04</span>
                      <div>
                        <small>{t('CONTROLLED METHOD', 'PHƯƠNG PHÁP KIỂM SOÁT')}</small>
                        <b>{t('Required execution sequence', 'Trình tự bắt buộc thực hiện')}</b>
                      </div>
                    </div>
                    <ol>
                      {guide.steps.map((step, index) => (
                        <li key={step}><span>{index + 1}</span><p>{step}</p></li>
                      ))}
                    </ol>
                  </section>
                  <div className="policy-basis">
                    <span>i</span>
                    <div>
                      <small>{t('DEMO POLICY BASIS', 'CƠ SỞ POLICY DEMO')}</small>
                      <p>{guide.policy}</p>
                      <em>Thread #{run.thread_id.slice(0, 8)} · {t('Decision stored in SQLite audit', 'Quyết định đã lưu vào audit SQLite')}</em>
                    </div>
                  </div>
                </>
              )}
              {run.status === 'INTERRUPTED' && (
                <div className="hitl-box">
                  <span>!</span>
                  <div>
                    <b>{t('QC confirmation required', 'Cần QC xác nhận')}</b>
                    <p>
                      {t(
                        'The graph is checkpointed. Choose an action to resume this exact thread.',
                        'Graph đã lưu checkpoint. Chọn hành động để tiếp tục đúng thread này.',
                      )}
                    </p>
                    <textarea
                      value={humanReason}
                      onChange={(event) => setHumanReason(event.target.value)}
                      aria-label={t('QC reason', 'Lý do QC')}
                    />
                    <div>
                      <button
                        disabled={running}
                        onClick={() => onResume('REJECT')}
                      >
                        {t('Reject finding', 'Không xác nhận lỗi')}
                      </button>
                      <button
                        className="primary"
                        disabled={running}
                        onClick={() => onResume('APPROVE')}
                      >
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
                  'Select an example and press Start inspection. The decision will appear only after its nodes execute.',
                  'Chọn một ví dụ và bấm Bắt đầu kiểm tra. Quyết định chỉ xuất hiện sau khi các node thực thi.',
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

function RunList({
  title,
  subtitle,
  runs,
  cases,
  empty,
  onOpen,
  onClear,
  t,
  lang,
}: {
  title: string;
  subtitle: string;
  runs: GraphRun[];
  cases: MockCase[];
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
          runs.map((run) => {
            const item = cases.find(
              (entry) => entry.vehicle_id === run.state.vehicle_id,
            );
            return (
              <button key={run.thread_id} onClick={() => onOpen(run)}>
                <div className="run-vehicle">
                  {item ? (
                    <img
                      src={`${API}${item.image_url}`}
                      alt={item.case_title}
                    />
                  ) : (
                    <span>QC</span>
                  )}
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
            );
          })
        ) : (
          <div className="empty-state">
            <span>◇</span>
            <b>{empty}</b>
            <p>
              {t(
                'Start with one of the image-backed examples in Agent inspection.',
                'Hãy bắt đầu bằng một ví dụ có ảnh trong màn hình Kiểm tra bằng Agent.',
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
  cases,
  onOpen,
  t,
  lang,
}: {
  runs: GraphRun[];
  cases: MockCase[];
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
          {runs.map((run) => {
            const item = cases.find(
              (entry) => entry.vehicle_id === run.state.vehicle_id,
            );
            return (
              <button key={run.thread_id} onClick={() => onOpen(run)}>
                <span className={`decision-dot ${outcomeTone(run)}`} />
                <span>
                  <b>{run.state.vehicle_id}</b>
                  <small>
                    {item?.case_title || pretty(run.state.defect_type)}
                  </small>
                </span>
                <strong>{actionLabel(run.state, lang)}</strong>
                <StatusPill run={run} t={t} />
              </button>
            );
          })}
        </div>
      ) : (
        <div className="empty-inline">
          {t(
            'No inspections yet — start the first example.',
            'Chưa có inspection — hãy chạy ví dụ đầu tiên.',
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
      'Detector mock đã trả kết quả phát hiện, confidence và vùng bbox.',
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
