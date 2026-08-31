import { createFileRoute } from "@tanstack/react-router";
import { motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Search } from "lucide-react";
import type { HistoryRow, Verdict } from "@/lib/qc-data";
import { Field, Panel, VerdictBadge } from "@/components/qc/primitives";
import { cn } from "@/lib/utils";
import { assetUrl } from "@/lib/auth";
import { formatZoneName } from "@/lib/detection-geometry";
import { useAgentRuns } from "@/lib/queries";
import type { GraphRun } from "@/lib/api-types";

export const Route = createFileRoute("/history")({
  head: () => ({
    meta: [
      { title: "Inspection History — AUTO QC Station 03" },
      {
        name: "description",
        content:
          "Searchable inspection log with AI verdicts, confidence, defect evidence, human decisions and full audit trail.",
      },
      { property: "og:title", content: "Inspection History — AUTO QC Station 03" },
      {
        property: "og:description",
        content: "Filterable QC inspection log with camera evidence and audit trail per vehicle.",
      },
    ],
  }),
  component: InspectionHistory,
});

const results = ["ALL", "PASS", "FAIL", "HITL"] as const;
const types = ["ALL", "Scratch", "Dent"] as const;

type Row = HistoryRow & { threadId: string; enrichedCount: number };

function verdictFor(run: GraphRun): Verdict {
  if (run.status === "INTERRUPTED") return "HITL";
  return run.state.final_status === "PASS" ? "PASS" : "FAIL";
}

function toRow(run: GraphRun): Row {
  const s = run.state;
  const defects = s.enriched_defects?.length ?? (s.defect_detected ? 1 : 0);
  return {
    threadId: run.thread_id,
    time: s._persisted_at ?? s.qc_decision_record?.created_at ?? "—",
    vin: s.vehicle_id,
    model: s.vehicle_model,
    result: verdictFor(run),
    defects,
    confidence: s.confidence != null ? Math.round(s.confidence * (s.confidence <= 1 ? 100 : 1)) : 0,
    severity: (s.severity as HistoryRow["severity"]) || "—",
    defectType: s.defect_type || s.classified_defect_code || "—",
    enrichedCount: defects,
  };
}

function formatTime(time: string): string {
  if (!time || time === "—") return "—";
  const d = new Date(time);
  if (Number.isNaN(d.getTime())) return time;
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function toCsv(rows: Row[]): string {
  const headers = [
    "Time",
    "VIN",
    "Model",
    "Result",
    "Defects",
    "AI conf.",
    "Severity",
    "Defect type",
  ];
  const lines = rows.map((r) =>
    [
      r.time,
      r.vin,
      r.model,
      r.result,
      r.defects,
      `${r.confidence}%`,
      r.severity,
      r.defectType,
    ]
      .map((v) => `"${String(v).replace(/"/g, '""')}"`)
      .join(","),
  );
  return [headers.join(","), ...lines].join("\n");
}

function downloadCsv(rows: Row[]) {
  const blob = new Blob([toCsv(rows)], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `inspection-history-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function InspectionHistory() {
  const { data: runs, isLoading, isError } = useAgentRuns();
  const [result, setResult] = useState<(typeof results)[number]>("ALL");
  const [type, setType] = useState<(typeof types)[number]>("ALL");
  const [query, setQuery] = useState("");
  const [minConf, setMinConf] = useState(0);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 15;

  const allRows = useMemo(() => (runs ?? []).map(toRow), [runs]);

  const rows = useMemo(
    () =>
      allRows.filter(
        (r) =>
          (result === "ALL" || r.result === result) &&
          (type === "ALL" || r.defectType === type) &&
          r.confidence >= minConf &&
          (query === "" || r.vin.toLowerCase().includes(query.toLowerCase())),
      ),
    [allRows, result, type, minConf, query],
  );

  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pagedRows = useMemo(
    () => rows.slice((currentPage - 1) * pageSize, currentPage * pageSize),
    [rows, currentPage],
  );

  const selected = rows.find((r) => r.threadId === selectedThreadId) ?? pagedRows[0] ?? null;

  useEffect(() => {
    setPage(1);
  }, [result, type, minConf, query]);
  const selectedRun = runs?.find((r) => r.thread_id === selected?.threadId);
  const selectedEvidence = selectedRun?.state.camera_evidence ?? [];

  return (
    <div className="space-y-4">
      <header className="panel flex flex-wrap items-end justify-between gap-4 px-5 py-4">
        <div>
          <h1 className="font-mono text-xl font-bold tracking-[0.18em] text-foreground">
            LỊCH SỬ INSPECTION
          </h1>
          <p className="mt-1 font-mono text-[11px] tracking-wider text-muted-foreground">
            {allRows.length} BẢN GHI
            {isLoading ? " · ĐANG TẢI…" : isError ? " · MẤT KẾT NỐI BACKEND" : ""}
          </p>
        </div>
        <button
          onClick={() => downloadCsv(rows)}
          disabled={rows.length === 0}
          className="inline-flex items-center gap-2 rounded-sm border border-border px-3 py-1.5 font-mono text-[11px] tracking-[0.14em] text-muted-foreground transition-colors hover:border-info/45 hover:text-info disabled:opacity-40"
        >
          <Download className="size-3.5" /> XUẤT CSV
        </button>
      </header>

      <div className="panel flex flex-wrap items-center gap-5 px-4 py-3">
        <label className="flex items-center gap-2 rounded-sm border border-border bg-surface-2 px-2.5 py-1.5">
          <Search className="size-3.5 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="TÌM VIN"
            className="w-40 bg-transparent font-mono text-[11px] tracking-wider text-foreground outline-none placeholder:text-muted-foreground/70"
          />
        </label>
        <div className="flex items-center gap-2">
          <span className="label-caps">Kết quả</span>
          {results.map((r) => (
            <button
              key={r}
              onClick={() => setResult(r)}
              className={cn(
                "rounded-sm border px-2.5 py-1 font-mono text-[11px] tracking-[0.12em] transition-colors",
                result === r
                  ? "border-info/45 bg-info/10 text-info"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {r}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="label-caps">Loại lỗi</span>
          {types.map((t) => (
            <button
              key={t}
              onClick={() => setType(t)}
              className={cn(
                "rounded-sm border px-2.5 py-1 font-mono text-[11px] tracking-[0.12em] transition-colors",
                type === t
                  ? "border-warning/45 bg-warning/10 text-warning"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {t.toUpperCase()}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2">
          <span className="label-caps">Độ tin cậy tối thiểu</span>
          <input
            type="range"
            min={0}
            max={100}
            value={minConf}
            onChange={(e) => setMinConf(Number(e.target.value))}
            className="w-32 accent-[var(--color-info)]"
          />
          <span className="font-mono text-[11px] text-info">{minConf}%</span>
        </label>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_1fr]">
        <Panel title={`Bản ghi (${rows.length})`} bodyClassName="p-0">
          <div className="max-h-[560px] overflow-auto">
            <table className="w-full border-collapse text-left">
              <thead className="sticky top-0 bg-surface-2">
                <tr>
                  {[
                    "Thời gian",
                    "VIN",
                    "Model",
                    "Kết quả",
                    "Số lỗi",
                    "Độ tin cậy AI",
                  ].map((h) => (
                    <th key={h} className="label-caps px-3 py-2 font-normal">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pagedRows.map((r) => (
                  <tr
                    key={r.threadId}
                    onClick={() => setSelectedThreadId(r.threadId)}
                    className={cn(
                      "cursor-pointer border-t border-border font-mono text-xs transition-colors",
                      selected?.threadId === r.threadId ? "bg-info/10" : "hover:bg-surface-2",
                    )}
                  >
                    <td className="px-3 py-2 text-muted-foreground">{formatTime(r.time)}</td>
                    <td className="px-3 py-2 text-foreground">{r.vin}</td>
                    <td className="px-3 py-2 text-muted-foreground">{r.model}</td>
                    <td className="px-3 py-2">
                      <VerdictBadge verdict={r.result} />
                    </td>
                    <td className="px-3 py-2 tabular-nums text-foreground">{r.defects}</td>
                    <td
                      className={cn(
                        "px-3 py-2 tabular-nums",
                        r.confidence < 70 ? "text-warning" : "text-success",
                      )}
                    >
                      {r.confidence}%
                    </td>
                  </tr>
                ))}
                {rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-3 py-8 text-center font-mono text-[11px] tracking-wider text-muted-foreground"
                    >
                      {isLoading
                        ? "ĐANG TẢI DANH SÁCH…"
                        : isError
                          ? "MẤT KẾT NỐI BACKEND"
                          : "KHÔNG CÓ BẢN GHI PHÙ HỢP BỘ LỌC"}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          {rows.length > 0 ? (
            <div className="flex items-center justify-between border-t border-border px-3 py-2">
              <span className="font-mono text-[11px] tracking-wider text-muted-foreground">
                TRANG {currentPage}/{pageCount} · {rows.length} BẢN GHI
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-1 font-mono text-[11px] tracking-[0.12em] text-muted-foreground transition-colors hover:border-info/45 hover:text-info disabled:opacity-40"
                >
                  <ChevronLeft className="size-3.5" /> TRƯỚC
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                  disabled={currentPage === pageCount}
                  className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-1 font-mono text-[11px] tracking-[0.12em] text-muted-foreground transition-colors hover:border-info/45 hover:text-info disabled:opacity-40"
                >
                  SAU <ChevronRight className="size-3.5" />
                </button>
              </div>
            </div>
          ) : null}
        </Panel>

        {selected ? (
          <motion.div
            key={selected.threadId}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Panel
              title={`Chi tiết inspection — ${selected.vin}`}
              right={<VerdictBadge verdict={selected.result} />}
            >
              <div className="grid grid-cols-3 gap-2">
                {selectedEvidence.length > 0 ? (
                  selectedEvidence.map((e) => {
                    const url = assetUrl(e.image_url || e.image_path);
                    return (
                      <div
                        key={e.camera_id}
                        className="relative overflow-hidden rounded-sm border border-border"
                      >
                        {url ? (
                          <img
                            src={url}
                            alt={`${e.camera_id} capture for ${selected.vin}`}
                            loading="lazy"
                            width={1024}
                            height={640}
                            className="aspect-[16/10] w-full object-cover opacity-85"
                          />
                        ) : (
                          <div className="flex aspect-[16/10] w-full items-center justify-center bg-surface-2 font-mono text-[10px] tracking-wider text-muted-foreground">
                            KHÔNG CÓ ẢNH
                          </div>
                        )}
                        <div className="scan-lines pointer-events-none absolute inset-0" />
                        <span className="absolute left-1.5 top-1.5 font-mono text-[10px] tracking-wider text-foreground">
                          {e.camera_id}
                        </span>
                      </div>
                    );
                  })
                ) : (
                  <div className="col-span-3 py-6 text-center font-mono text-[11px] tracking-wider text-muted-foreground">
                    KHÔNG CÓ ẢNH CAMERA CHO LẦN KIỂM TRA NÀY
                  </div>
                )}
              </div>

              <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-3">
                <Field label="Mã inspection" value={selected.threadId.slice(0, 8)} />
                <Field label="Thời gian" value={formatTime(selected.time)} tone="info" />
                <Field label="Model" value={selected.model} />
                <Field
                  label="Độ tin cậy AI"
                  value={`${selected.confidence}%`}
                  tone={selected.confidence < 70 ? "warning" : "success"}
                />
                <Field label="Số lỗi" value={selected.defects} tone="danger" />
                <Field label="Mức độ" value={selected.severity} tone="warning" />
                <Field label="Loại lỗi" value={selected.defectType} />
                <Field
                  label="Quyết định con người"
                  value={selected.result === "HITL" ? "ĐANG CHỜ" : "—"}
                  {...(selected.result === "HITL" ? { tone: "warning" as const } : {})}
                />
              </div>

              <div className="mt-4 rounded-sm border border-border bg-surface-2 p-3">
                <div className="label-caps">Phát hiện của AI</div>
                <ul className="mt-1 space-y-1">
                  {(selectedRun?.state.enriched_defects ?? []).map((d) => (
                    <li
                      key={d.detection_id}
                      className="flex items-center justify-between font-mono text-[11px] text-foreground"
                    >
                      <span>
                        {d.class_name} — {formatZoneName(d.zone_name)}
                      </span>
                      <span className="text-muted-foreground">
                        {d.camera_id} · {Math.round(d.confidence * (d.confidence <= 1 ? 100 : 1))}%
                      </span>
                    </li>
                  ))}
                  {selected.defects === 0 ? (
                    <li className="font-mono text-[11px] text-success">
                      KHÔNG PHÁT HIỆN LỖI VƯỢT NGƯỠNG
                    </li>
                  ) : null}
                </ul>
                <p className="mt-2 text-sm text-muted-foreground">
                  {selected.result === "PASS"
                    ? "Xe đạt — toàn bộ bề mặt chụp được nằm trong ngưỡng cho phép."
                    : selectedRun?.state.reason ||
                      "Xem phần phát hiện AI phía trên để biết cơ sở của quyết định này."}
                </p>
              </div>
            </Panel>
          </motion.div>
        ) : null}
      </div>
    </div>
  );
}
