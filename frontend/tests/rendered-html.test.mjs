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

test("inspection source streams real LangGraph node updates", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /\/inspections\/stream/);
  assert.match(page, /NodeTimeline/);
  assert.match(page, /prepare_input/);
  assert.match(page, /verify_defect/);
  assert.match(page, /human_review/);
  assert.match(page, /mock_scenario: selectedCase\.graph_scenario/);
  assert.match(page, /mock_detection/);
  assert.match(page, /panel: selectedCase\.panel/);
});

test("Gemini and branch-selection controls are absent", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(page, /Gemini|agent\/explain|graphScenario|setScenario/);
  assert.match(page, /The mock profile is attached to the image/);
});

test("history can clear persisted Agent traces", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /method: ['"]DELETE['"]/);
  assert.match(page, /Clear history/);
  assert.match(page, /window\.confirm/);
});

test("dashboard shows only the latest configured run per vehicle", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /caseVehicleIds/);
  assert.match(page, /new Map\(/);
  assert.match(page, /item\.state\.vehicle_id !== run\.state\.vehicle_id/);
  assert.match(page, /latest result per vehicle/);
});

test("decision panel uses Vietnamese-safe typography and detailed QC guidance", async () => {
  const [page, layout, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);
  assert.match(layout, /globals\.css\?inline/);
  assert.doesNotMatch(layout, /next\/font|Noto_Sans/);
  assert.match(page, /PHƯƠNG PHÁP KIỂM SOÁT/);
  assert.match(page, /ĐIỀU KIỆN RELEASE/);
  assert.match(page, /CƠ SỞ POLICY DEMO/);
  assert.match(css, /\.decision-method/);
  assert.match(css, /\.safety-gates/);
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
