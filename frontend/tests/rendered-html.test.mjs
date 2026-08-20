import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the focused Visual QC workstation", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Visual QC Agent \| FNS Workstation/);
  assert.match(html, /Kiểm tra bằng Agent/);
  assert.match(html, /Hàng đợi QC/);
  assert.match(html, /Một inspection\. Một workflow/);
  assert.doesNotMatch(html, /Gemini|Mô phỏng CV|Dấu vết Agent/i);
});

test("inspection source is upload-only and uses real model output", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /\/inspections\/from-image/);
  assert.match(page, /NodeTimeline/);
  assert.match(page, /prepare_input/);
  assert.match(page, /verify_defect/);
  assert.match(page, /human_review/);
  assert.doesNotMatch(page, /\/api\/evidence\/cases|\/assets\/train|selectedCase|mock_detection/);
  assert.match(page, /best\.pt/);
  assert.match(page, /form\.append\('zone_name', uploadedEvidence\.zoneName\)/);
});

test("overview introduces the project and inspection uses a focused vertical layout", async () => {
  const [page, theme] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/workstation.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /FNS BODY QUALITY · AI-ASSISTED INSPECTION/);
  assert.match(page, /MỤC TIÊU DỰ ÁN/);
  assert.match(page, /PHẠM VI MVP/);
  assert.match(page, /Local YOLO segmentation/);
  assert.match(theme, /\.project-grid/);
  assert.match(theme, /\.hero-system-card/);
  assert.match(theme, /\.decision-card \{ grid-column: 1\/-1/);
});

test("completed conditional LangGraph routes show 100 percent progress", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /run\?\.status === 'COMPLETED'[\s\S]*?\? 100/);
  assert.doesNotMatch(page, /completedNodes \/ 7/);
});

test("Gemini and frontend-authored model outputs are absent", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(page, /Gemini|agent\/explain|graphScenario|setScenario/);
  assert.doesNotMatch(page, /mock_detection|The mock profile is attached to the image/);
  assert.match(page, /primary video is converted to one inspection frame before best\.pt inference/i);
});

test("web uploads are sent to best.pt and model evidence is rendered", async () => {
  const [page, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /new FormData\(\)/);
  assert.match(page, /\/inspections\/from-image/);
  assert.match(page, /accept="image\/jpeg,image\/png,video\/mp4,video\/webm"/);
  assert.match(page, /segmentation-mask/);
  assert.match(page, /model_version/);
  assert.match(css, /\.upload-panel/);
  assert.match(css, /\.segmentation-mask/);
});

test("inspection focuses on one primary camera beside the Agent decision", async () => {
  const [page, theme, workstation] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/interface-system.css", import.meta.url), "utf8"),
    readFile(new URL("../app/workstation.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /CAM-FNS-FRONT/);
  assert.doesNotMatch(page, /SUPPORTING_CAMERAS|CAM-FNS-LEFT|CAM-FNS-RIGHT|CAM-FNS-REAR/);
  assert.match(page, /modelFrameFromFile/);
  assert.doesNotMatch(page, /className="evidence-console"/);
  assert.doesNotMatch(page, /className="camera-assessment"/);
  assert.match(page, /className="multiview-wall"/);
  assert.match(theme, /\.content-inspect \.multiview-wall/);
  assert.match(theme, /aspect-ratio: 16 \/ 10/);
  assert.match(theme, /grid-template-columns: minmax\(0, 2fr\) minmax\(320px, 1fr\)/);
  assert.doesNotMatch(theme, /\.content-inspect \.camera-assessment/);
  assert.doesNotMatch(theme, /\.content-inspect \.support-camera-label/);
  assert.doesNotMatch(theme, /\.support-camera\.camera-top/);
  assert.match(workstation, /\.shell \{ grid-template-columns: 224px minmax\(0, 1fr\); \}/);
});

test("history can clear persisted Agent traces", async () => {
  const [page, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/interface-system.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /method: ['"]DELETE['"]/);
  assert.match(page, /Clear history/);
  assert.match(page, /window\.confirm/);
  assert.match(page, /variant="history"/);
  assert.match(page, /history-thumb/);
  assert.match(page, /KÍCH THƯỚC \/ VỊ TRÍ/);
  assert.match(page, /classified_defect_code/);
  assert.match(css, /\.history-record/);
});

test("repeated defect alerts show a concise QC workflow and expose a DOCX report", async () => {
  const [page, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /Cảnh báo lặp lỗi/);
  assert.match(page, /api\/quality-alerts/);
  assert.match(page, /api\/quality-alerts\/report\.docx/);
  assert.match(page, /QualityAlertsPage/);
  assert.match(page, /CẦN XỬ LÝ/);
  assert.match(page, /affected_vehicle_ids/);
  assert.match(page, /HÀNH ĐỘNG NGAY/);
  assert.match(page, /KẾT LUẬN CỦA AGENT/);
  assert.match(page, /BẰNG CHỨNG TRỰC QUAN/);
  assert.match(page, /related_defect_codes/);
  assert.match(page, /alert-image-strip/);
  assert.match(page, /Đóng cảnh báo khi:/);
  assert.doesNotMatch(page, /TỔNG HỢP LỊCH SỬ KIỂM TRA/);
  assert.doesNotMatch(page, /PHÂN BỐ ĐIỀU PHỐI/);
  assert.doesNotMatch(page, /actionable_routing_command\}/);
  assert.doesNotMatch(page, /CÁC LẦN KIỂM TRA TẠO CẢNH BÁO/);
  assert.match(css, /\.trend-alert/);
  assert.match(css, /\.report-download/);
});

test("operational action and policy evidence dossier have distinct roles", async () => {
  const [page, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/workstation.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /HÀNH ĐỘNG VẬN HÀNH/);
  assert.match(page, /HỒ SƠ POLICY & AUDIT/);
  assert.match(page, /NGỮ CẢNH TRA CỨU/);
  assert.match(page, /CẢNH BÁO TÀI LIỆU/);
  assert.match(page, /Xem điều kiện policy và trích dẫn/);
  assert.match(page, /TRÍCH DẪN TÀI LIỆU/);
  assert.doesNotMatch(page, /KẾT LUẬN AGENT ĐỒNG NHẤT/);
  assert.doesNotMatch(page, /COPILOT PHÂN TÍCH/);
  assert.match(css, /\.decision-rationale/);
});

test("dashboard shows the latest uploaded run per vehicle", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /new Map\(/);
  assert.match(page, /item\.state\.vehicle_id !== run\.state\.vehicle_id/);
  assert.match(page, /latest result per vehicle/);
});

test("decision panel uses Vietnamese-safe typography and focused Agent guidance", async () => {
  const [page, layout, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);
  assert.match(layout, /globals\.css\?inline/);
  assert.doesNotMatch(layout, /next\/font|Noto_Sans/);
  assert.match(page, /2 · Phân loại/);
  assert.match(page, /3 · Policy áp dụng/);
  assert.match(page, /4 · Agent quyết định/);
  assert.match(page, /AGENT REASONING/);
  assert.match(page, /Ảnh hưởng cao/);
  assert.match(page, /Ảnh hưởng đáng chú ý/);
  assert.match(page, /Ảnh hưởng nhẹ/);
  assert.match(page, /Quyền test drive/);
  assert.match(page, /HỒ SƠ POLICY & AUDIT/);
  assert.match(css, /\.decision-facts/);
  assert.match(css, /"Segoe UI","Noto Sans"/);
});

test("runtime status is placed above the LangGraph runtime divider", async () => {
  const [page, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);
  assert.match(
    page,
    /className="runtime-stack"[\s\S]*className="notice"[\s\S]*LangGraph runtime/,
  );
  assert.match(css, /\.runtime-stack\{margin-top:auto/);
  assert.match(css, /\.sidebar \.notice\{/);
  assert.match(css, /\.sidebar footer\{[^}]*border-top:/);
  assert.doesNotMatch(css, /\.notice\{position:fixed/);
});

test("all primary views use the shared wide responsive interface system", async () => {
  const [page, layout, theme] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/interface-system.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /content content-\$\{view\}/);
  assert.match(layout, /interface-system\.css\?inline/);
  assert.match(theme, /\.content-overview/);
  assert.match(theme, /\.content-queue/);
  assert.match(theme, /\.content-history/);
  assert.match(theme, /\.content-alerts/);
  assert.match(theme, /max-width: 2200px/);
  assert.match(theme, /@media \(max-width: 760px\)/);
});

test("inspection swaps the in-panel live trace for the final QC output", async () => {
  const [page, theme] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/interface-system.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /<details className="decision-rationale policy-disclosure">/);
  assert.match(page, /className="decision-live-trace"/);
  assert.match(page, /running \? \(/);
  assert.doesNotMatch(page, /className="trace-card card trace-disclosure"/);
  assert.match(page, /Xem hồ sơ/);
  assert.doesNotMatch(page, /<section className="decision-rationale">/);
  assert.match(theme, /\.content-inspect \.camera-card \{[\s\S]*?grid-column: 1;/);
  assert.match(theme, /\.content-inspect \.decision-card \{[\s\S]*?grid-column: 2;[\s\S]*?grid-row: 1/);
  assert.match(theme, /\.content-inspect \.decision-live-trace/);
});

test("HITL checkpoint is a prominent and accessible QC action", async () => {
  const [page, theme] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/interface-system.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /CHECKPOINT KIỂM DUYỆT/);
  assert.match(page, /queue-record/);
  assert.match(page, /LÝ DO CẦN QC/);
  assert.match(page, /Mở kiểm duyệt/);
  assert.match(page, /className="hitl-actions"/);
  assert.match(page, /placeholder=\{t\(/);
  assert.match(theme, /\.content-inspect \.decision-card \.hitl-box/);
  assert.match(theme, /min-height: 104px/);
  assert.match(theme, /min-height: 64px/);
  assert.match(theme, /\.queue-record/);
});

test("operational explanation is never line-clamped", async () => {
  const theme = await readFile(
    new URL("../app/interface-system.css", import.meta.url),
    "utf8",
  );
  assert.match(
    theme,
    /\.content-inspect \.decision-card \.outcome p \{[\s\S]*?-webkit-line-clamp: unset;/,
  );
  assert.match(theme, /overflow-wrap: anywhere/);
});

test("QC defect registry exposes CV mapping, location, length and saved decisions", async () => {
  const [page, theme] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/interface-system.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /id: 'catalog'/);
  assert.match(page, /className="defect-registry-page"/);
  assert.match(page, /cv_label/);
  assert.match(page, /length_mm/);
  assert.match(page, /DEFECT LOCATION/);
  assert.match(page, /CHIỀU DÀI LỖI \(MM\)/);
  assert.match(theme, /\.defect-registry-page/);
  assert.match(theme, /\.registry-table/);
});
