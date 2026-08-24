import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import { AlertTriangle, ArrowRight, CircleCheck, Clock, Cpu, Video } from "lucide-react";
import { Dot, Meter, Panel } from "@/components/qc/primitives";
import { SystemStatusList } from "@/components/qc/SystemStatus";
import { cn } from "@/lib/utils";
import { assetUrl, profileDisplayName, useAuth } from "@/lib/auth";
import { useAgentRuns, useAgentStatus, useQualityAlerts } from "@/lib/queries";
import type { GraphRun } from "@/lib/api-types";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "QC Shift Overview — AUTO QC Station 03" },
      {
        name: "description",
        content:
          "Live shift KPIs, current vehicle inspection progress, camera health and attention alerts for QC station 03.",
      },
      { property: "og:title", content: "QC Shift Overview — AUTO QC Station 03" },
      {
        property: "og:description",
        content: "Shift KPIs, live inspection progress, camera health and realtime defect alerts.",
      },
    ],
  }),
  component: ShiftOverview,
});

const KNOWN_CAMERA_IDS = ["CAM-01", "CAM-02", "CAM-03", "CAM-04", "CAM-05"] as const;
const CAMERA_LABELS: Record<string, string> = {
  "CAM-01": "TRƯỚC",
  "CAM-02": "SAU",
  "CAM-03": "TRÁI",
  "CAM-04": "PHẢI",
  "CAM-05": "TRÊN / TOÀN CẢNH",
};

function Kpi({
  label,
  value,
  sub,
  tone = "default",
  children,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "default" | "success" | "danger" | "warning" | "info";
  children?: React.ReactNode;
}) {
  const toneRing =
    tone === "success"
      ? "border-success/35"
      : tone === "danger"
        ? "border-destructive/35"
        : tone === "warning"
          ? "border-warning/45 glow-warning"
          : tone === "info"
            ? "border-info/35"
            : "border-border";
  const toneText =
    tone === "success"
      ? "text-success"
      : tone === "danger"
        ? "text-destructive"
        : tone === "warning"
          ? "text-warning"
          : tone === "info"
            ? "text-info"
            : "text-foreground";
  return (
    <div className={cn("panel p-4", toneRing)}>
      <div className="label-caps">{label}</div>
      <div className={cn("mt-2 font-mono text-4xl font-bold tabular-nums leading-none", toneText)}>
        {value}
      </div>
      {sub ? <div className="mt-2 font-mono text-[11px] text-muted-foreground">{sub}</div> : null}
      {children}
    </div>
  );
}

/**
 * Most recent run per vehicle_id — the backend returns full run history, not a dedup'd list,
 * ordered newest-first (updated_at DESC, see agent/services/repository.py). Keep the first
 * occurrence of each vehicle_id so dedup keeps the newest run, not the oldest.
 */
function dedupeByVehicle(runs: GraphRun[]): GraphRun[] {
  const seen = new Set<string>();
  const result: GraphRun[] = [];
  for (const r of runs) {
    if (seen.has(r.state.vehicle_id)) continue;
    seen.add(r.state.vehicle_id);
    result.push(r);
  }
  return result;
}

function ShiftOverview() {
  const { profile } = useAuth();
  const runsQuery = useAgentRuns();
  const alertsQuery = useQualityAlerts();
  const statusQuery = useAgentStatus();

  const displayRuns = runsQuery.data ? dedupeByVehicle(runsQuery.data) : [];
  const inspected = displayRuns.length;
  const passCount = displayRuns.filter((r) => r.state.final_status === "PASS").length;
  const failCount = displayRuns.filter(
    (r) => r.status === "COMPLETED" && r.state.final_status && r.state.final_status !== "PASS",
  ).length;
  const hitlPending = displayRuns.filter((r) => r.status === "INTERRUPTED").length;
  const passRate = inspected ? Math.round((passCount / inspected) * 1000) / 10 : 0;
  const failRate = inspected ? Math.round((failCount / inspected) * 1000) / 10 : 0;

  // "Most recent" run: prefer one still waiting on QC, else the first (newest) run returned by
  // the backend (GET /agent/runs is ordered updated_at DESC).
  const latestRun =
    runsQuery.data?.find((r) => r.status === "INTERRUPTED") ?? runsQuery.data?.[0] ?? null;
  const trace = latestRun?.state.execution_trace ?? [];
  const engineOnline = statusQuery.data?.langgraph === "READY";

  const alerts = alertsQuery.data?.alerts ?? [];
  const attentionItems =
    alerts.length > 0
      ? alerts.map((a) => ({
          key: a.id,
          level: a.severity === "CRITICAL" ? ("critical" as const) : ("warning" as const),
          text: a.message_vi || a.message_en,
          time: a.last_seen,
        }))
      : [
          {
            key: "ok",
            level: "ok" as const,
            text: "Không có cảnh báo — mọi hệ thống đang hoạt động bình thường",
            time: "—",
          },
        ];

  // No backend endpoint exposes live per-camera FPS/confidence telemetry — only per-inspection
  // evidence images exist. Derive each camera's tile from the most recent run's real evidence
  // instead of showing fabricated numbers.
  const cameraTiles = KNOWN_CAMERA_IDS.map((id) => {
    const evidence = latestRun?.state.camera_evidence?.find((e) => e.camera_id === id);
    const result = latestRun?.state.camera_results?.find((r) => r.camera_id === id);
    return {
      id,
      label: CAMERA_LABELS[id],
      captured: !!evidence,
      image: assetUrl(evidence?.image_url || evidence?.image_path),
      defectDetected: result?.defect_detected ?? false,
    };
  });
  const capturedCount = cameraTiles.filter((c) => c.captured).length;

  return (
    <div className="space-y-4">
      <header className="panel flex flex-wrap items-end justify-between gap-4 px-5 py-4">
        <div>
          <h1 className="font-mono text-xl font-bold tracking-[0.18em] text-foreground">
            TỔNG QUAN CA LÀM VIỆC
          </h1>
          <p className="mt-1 font-mono text-[11px] tracking-wider text-muted-foreground">
            TRẠM {latestRun?.state.station_id || "—"} · NGƯỜI VẬN HÀNH{" "}
            {profileDisplayName(profile).toUpperCase()}
          </p>
        </div>
        <div
          className={cn(
            "flex items-center gap-2 rounded-sm border px-3 py-1.5 font-mono text-xs tracking-[0.16em]",
            engineOnline
              ? "border-success/40 bg-success/10 text-success glow-success"
              : "border-destructive/40 bg-destructive/10 text-destructive",
          )}
        >
          <Dot state={engineOnline ? "ok" : "down"} />{" "}
          {engineOnline ? "HỆ THỐNG HOẠT ĐỘNG" : "MẤT KẾT NỐI BACKEND"}
        </div>
      </header>

      {runsQuery.isError || alertsQuery.isError ? (
        <div className="panel border-destructive/40 bg-destructive/5 px-4 py-2.5 font-mono text-[11px] tracking-wider text-destructive">
          MẤT KẾT NỐI BACKEND — đang hiển thị dữ liệu gần nhất đã tải được
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-5">
        <Kpi
          label="Trạng thái AI Engine"
          value={engineOnline ? "HOẠT ĐỘNG" : "LỖI"}
          tone={engineOnline ? "success" : "danger"}
          sub={statusQuery.data?.reasoning?.mode || "—"}
        >
          <div className="mt-3">
            <Meter value={engineOnline ? 100 : 0} tone={engineOnline ? "success" : "danger"} />
          </div>
        </Kpi>
        <Kpi
          label="Xe đã kiểm"
          value={runsQuery.isPending ? "—" : String(inspected)}
          sub="Số xe khác nhau trong phiên này"
          tone="info"
        />
        <Kpi
          label="PASS"
          value={runsQuery.isPending ? "—" : String(passCount)}
          sub={`${passRate}% tỷ lệ đạt`}
          tone="success"
        >
          <div className="mt-3">
            <Meter value={passRate} tone="success" />
          </div>
        </Kpi>
        <Kpi
          label="FAIL"
          value={runsQuery.isPending ? "—" : String(failCount)}
          sub={`${failRate}% tỷ lệ lỗi`}
          tone="danger"
        >
          <div className="mt-3">
            <Meter value={failRate} tone="danger" />
          </div>
        </Kpi>
        <Kpi
          label="HITL Pending"
          value={runsQuery.isPending ? "—" : String(hitlPending)}
          sub="Chờ nhân viên xác nhận"
          tone="warning"
        >
          <Link
            to="/hitl"
            className="mt-3 inline-flex items-center gap-1.5 font-mono text-[11px] tracking-[0.12em] text-warning hover:underline"
          >
            MỞ HÀNG ĐỢI <ArrowRight className="size-3" />
          </Link>
        </Kpi>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <Panel
          title="Inspection gần nhất"
          right={
            <span className="flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] text-info">
              <Dot state={latestRun ? "info" : "ok"} />
              {latestRun ? "INSPECTION GẦN NHẤT" : "CHƯA CÓ INSPECTION"}
            </span>
          }
        >
          {latestRun ? (
            <>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="label-caps">Xe hiện tại</div>
                  <div className="mt-1 font-mono text-2xl font-bold text-foreground">
                    {latestRun.state.vehicle_id}
                  </div>
                  <div className="mt-1 font-mono text-[11px] tracking-wider text-muted-foreground">
                    {latestRun.state.vehicle_model} · {latestRun.state.zone_name} · #
                    {latestRun.state.inspection_id}
                  </div>
                </div>
                <div className="text-right">
                  <div className="label-caps">Trạng thái</div>
                  <div
                    className={cn(
                      "font-mono text-2xl font-bold tabular-nums",
                      latestRun.status === "INTERRUPTED" ? "text-warning" : "text-success",
                    )}
                  >
                    {latestRun.status === "INTERRUPTED" ? "CHỜ DUYỆT" : "HOÀN TẤT"}
                  </div>
                </div>
              </div>

              <ol className="mt-5 space-y-1.5">
                {trace.length > 0 ? (
                  trace.map((step, i) => (
                    <li
                      key={`${step.node}-${i}`}
                      className="flex items-center justify-between gap-3 rounded-sm border border-border bg-surface-2 px-3 py-2"
                    >
                      <span className="min-w-0 truncate font-mono text-xs text-foreground">
                        {step.node}
                      </span>
                      <span className="shrink-0 font-mono text-[10px] tracking-wider text-muted-foreground">
                        {step.status}
                      </span>
                    </li>
                  ))
                ) : (
                  <li className="rounded-sm border border-border bg-surface-2 px-3 py-2 font-mono text-xs text-muted-foreground">
                    Chưa có nhật ký thực thi cho lần kiểm tra này.
                  </li>
                )}
              </ol>

              <div className="mt-5 flex flex-wrap items-center gap-3">
                <Link
                  to="/inspection"
                  className="inline-flex items-center gap-2 rounded-sm border border-info/45 bg-info/10 px-4 py-2 font-mono text-xs tracking-[0.16em] text-info transition-colors hover:bg-info/20"
                >
                  <Cpu className="size-4" /> MỞ MÀN HÌNH INSPECTION
                </Link>
                <span className="flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
                  <Clock className="size-3.5" /> Thread {latestRun.thread_id}
                </span>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-start gap-3 py-6">
              <p className="text-sm text-muted-foreground">
                Chưa ghi nhận lần kiểm tra nào trong phiên này.
              </p>
              <Link
                to="/inspection"
                className="inline-flex items-center gap-2 rounded-sm border border-info/45 bg-info/10 px-4 py-2 font-mono text-xs tracking-[0.16em] text-info transition-colors hover:bg-info/20"
              >
                <Cpu className="size-4" /> MỞ MÀN HÌNH INSPECTION
              </Link>
            </div>
          )}
        </Panel>

        <Panel
          title="Cần chú ý"
          right={<span className="label-caps">realtime</span>}
          bodyClassName="p-3"
        >
          <ul className="space-y-2">
            {attentionItems.map((a) => {
              const styles =
                a.level === "critical"
                  ? "border-destructive/40 bg-destructive/10 text-destructive"
                  : a.level === "warning"
                    ? "border-warning/40 bg-warning/10 text-warning"
                    : "border-success/35 bg-success/5 text-success";
              const Icon = a.level === "ok" ? CircleCheck : AlertTriangle;
              return (
                <motion.li
                  key={a.key}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={cn("rounded-sm border px-3 py-2.5", styles)}
                >
                  <div className="flex items-start gap-2">
                    <Icon className="mt-0.5 size-4 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm leading-snug text-foreground">{a.text}</p>
                      <p className="mt-0.5 font-mono text-[10px] tracking-wider opacity-80">
                        {a.time}
                      </p>
                    </div>
                  </div>
                </motion.li>
              );
            })}
          </ul>
          <div className="mt-3 border-t border-border pt-3">
            <SystemStatusList compact />
          </div>
        </Panel>
      </div>

      <Panel
        title="Trạng thái camera (lần chụp gần nhất)"
        right={
          <span className="flex items-center gap-2 font-mono text-[11px] text-success">
            <Video className="size-3.5" /> {capturedCount}/{KNOWN_CAMERA_IDS.length} ĐÃ CHỤP
          </span>
        }
      >
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
          {cameraTiles.map((c) => (
            <div
              key={c.id}
              className={cn(
                "overflow-hidden rounded-sm border bg-surface-2",
                c.defectDetected ? "border-warning/45" : "border-border",
              )}
            >
              {c.image ? (
                <img
                  src={c.image}
                  alt={`${c.id} lần chụp gần nhất`}
                  loading="lazy"
                  width={640}
                  height={360}
                  className="aspect-video w-full object-cover opacity-90"
                />
              ) : (
                <div className="flex aspect-video w-full items-center justify-center bg-surface font-mono text-[10px] tracking-wider text-muted-foreground">
                  CHƯA CÓ ẢNH
                </div>
              )}
              <div className="p-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm font-semibold text-foreground">{c.id}</span>
                  <span
                    className={cn(
                      "flex items-center gap-1.5 font-mono text-[10px] tracking-[0.14em]",
                      c.captured ? "text-success" : "text-muted-foreground",
                    )}
                  >
                    <Dot state={c.captured ? "ok" : "down"} pulse={false} />
                    {c.captured ? "ĐÃ CHỤP" : "CHƯA CHỤP"}
                  </span>
                </div>
                <div className="label-caps mt-1">{c.label}</div>
                {c.captured ? (
                  <div className="mt-2 font-mono text-[11px] text-muted-foreground">
                    Kết quả:{" "}
                    <span className={c.defectDetected ? "text-warning" : "text-success"}>
                      {c.defectDetected ? "PHÁT HIỆN LỖI" : "OK"}
                    </span>
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
