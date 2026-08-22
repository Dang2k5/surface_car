import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Images, Search, TrendingUp, Wrench } from "lucide-react";
import type { WarningLevel } from "@/lib/qc-data";
import { LevelBadge, Panel } from "@/components/qc/primitives";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useQualityAlerts, useTrend } from "@/lib/queries";
import type { QualityAlert } from "@/lib/api-types";

type DisplayPattern = {
  id: string;
  defect: string;
  location: string;
  occurrences: number;
  window: number;
  level: WarningLevel;
  vehicles: string[];
  summary: string;
};

function levelFromSeverity(severity: QualityAlert["severity"]): WarningLevel {
  return severity === "CRITICAL" ? "CRITICAL" : severity === "WARNING" ? "WARNING" : "WATCH";
}

function toPattern(alert: QualityAlert): DisplayPattern {
  return {
    id: alert.id,
    defect: alert.defect_type,
    location: alert.zone_name,
    occurrences: alert.occurrence_count,
    window: alert.window_size,
    level: levelFromSeverity(alert.severity),
    vehicles: alert.affected_vehicle_ids,
    summary: alert.message_vi || alert.message_en,
  };
}

export const Route = createFileRoute("/warnings")({
  head: () => ({
    meta: [
      { title: "Early Defect Warning — AUTO QC Station 03" },
      {
        name: "description",
        content:
          "Realtime detection of repeated surface defect patterns across consecutive vehicles with severity levels and trend charts.",
      },
      { property: "og:title", content: "Early Defect Warning — AUTO QC Station 03" },
      {
        property: "og:description",
        content:
          "Repeated defect pattern detection with realtime frequency charts and escalation actions.",
      },
    ],
  }),
  component: EarlyWarnings,
});

function EarlyWarnings() {
  const { role } = useAuth();
  const { data: alertSummary, isLoading, isError } = useQualityAlerts();
  const { data: trendRows } = useTrend("hour");
  const [investigating, setInvestigating] = useState<string[]>([]);

  const patterns = useMemo(() => (alertSummary?.alerts ?? []).map(toPattern), [alertSummary]);
  const criticalCount = patterns.filter((p) => p.level === "CRITICAL").length;
  const levelCounts = useMemo(() => {
    const counts: Record<WarningLevel, number> = { NORMAL: 0, WATCH: 0, WARNING: 0, CRITICAL: 0 };
    for (const p of patterns) counts[p.level] += 1;
    return counts;
  }, [patterns]);

  return (
    <div className="space-y-4">
      <header className="panel flex flex-wrap items-end justify-between gap-4 px-5 py-4">
        <div>
          <h1 className="font-mono text-xl font-bold tracking-[0.18em] text-foreground">
            CẢNH BÁO LỖI SỚM
          </h1>
          <p className="mt-1 font-mono text-[11px] tracking-wider text-muted-foreground">
            PHÁT HIỆN LỖI LẶP LẠI TRÊN NHIỀU XE LIÊN TIẾP · CỬA SỔ{" "}
            {alertSummary?.window_hours ?? "—"}H
          </p>
        </div>
        {criticalCount > 0 ? (
          <motion.div
            animate={{ opacity: [1, 0.55, 1] }}
            transition={{ duration: 2.2, repeat: Infinity }}
            className="flex items-center gap-2 rounded-sm border border-destructive/50 bg-destructive/10 px-3 py-1.5 font-mono text-xs tracking-[0.14em] text-destructive glow-danger"
          >
            PHÁT HIỆN LỖI LẶP LẠI
          </motion.div>
        ) : null}
      </header>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <Panel
          title="Tần suất / xu hướng lỗi (theo giờ)"
          right={<span className="label-caps">supervisor</span>}
        >
          {role !== "QC_SUPERVISOR" ? (
            <div className="flex h-[300px] items-center justify-center px-4 text-center text-sm text-muted-foreground">
              Đăng nhập với tài khoản QC_SUPERVISOR để xem biểu đồ xu hướng lịch sử.
            </div>
          ) : (
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={trendRows ?? []}
                  margin={{ top: 8, right: 8, left: -18, bottom: 0 }}
                >
                  <defs>
                    {[
                      ["scratch", "var(--color-chart-3)"],
                      ["dent", "var(--color-chart-2)"],
                    ].map(([id, color]) => (
                      <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={color} stopOpacity={0.45} />
                        <stop offset="100%" stopColor={color} stopOpacity={0.02} />
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="group_value"
                    stroke="var(--color-muted-foreground)"
                    tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
                  />
                  <YAxis
                    stroke="var(--color-muted-foreground)"
                    tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--color-popover)",
                      border: "1px solid var(--color-border)",
                      borderRadius: 6,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                    }}
                  />
                  <Legend wrapperStyle={{ fontFamily: "var(--font-mono)", fontSize: 11 }} />
                  <Area
                    type="monotone"
                    dataKey="scratch_count"
                    name="Scratch"
                    stroke="var(--color-chart-3)"
                    fill="url(#scratch)"
                    strokeWidth={2}
                    animationDuration={700}
                  />
                  <Area
                    type="monotone"
                    dataKey="dent_count"
                    name="Dent"
                    stroke="var(--color-chart-2)"
                    fill="url(#dent)"
                    strokeWidth={2}
                    animationDuration={700}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        <Panel title="Ngưỡng mức độ cảnh báo">
          <div className="grid grid-cols-4 gap-2">
            {(["NORMAL", "WATCH", "WARNING", "CRITICAL"] as const).map((lvl, i) => (
              <div
                key={lvl}
                className={cn(
                  "rounded-sm border bg-surface-2 p-3 text-center",
                  i === 3 && "border-destructive/45",
                  i === 2 && "border-warning/45",
                  i === 1 && "border-info/40",
                  i === 0 && "border-border",
                )}
              >
                <LevelBadge level={lvl} />
                <div className="mt-2 font-mono text-2xl font-bold text-foreground tabular-nums">
                  {levelCounts[lvl]}
                </div>
                <div className="label-caps mt-0.5">cảnh báo đang mở</div>
              </div>
            ))}
          </div>
          {isLoading ? (
            <p className="mt-4 text-sm text-muted-foreground">Đang tải cảnh báo chất lượng…</p>
          ) : isError ? (
            <p className="mt-4 text-sm text-destructive">
              Không thể kết nối tới nguồn cảnh báo chất lượng của backend.
            </p>
          ) : patterns.length === 0 ? (
            <p className="mt-4 text-sm text-muted-foreground">Không phát hiện lỗi lặp lại nào.</p>
          ) : (
            <ul className="mt-4 space-y-2">
              {patterns.map((p) => (
                <li
                  key={p.id}
                  className="flex items-center justify-between gap-3 rounded-sm border border-border bg-surface-2 px-3 py-2"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm text-foreground">
                      {p.defect} — {p.location}
                    </span>
                    <span className="label-caps block">
                      {p.occurrences}/{p.window}
                    </span>
                  </span>
                  <LevelBadge level={p.level} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {patterns.slice(0, 2).map((p) => (
          <motion.div
            key={p.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn(
              "panel p-4",
              p.level === "CRITICAL" && "border-destructive/45 glow-danger",
              p.level === "WARNING" && "border-warning/45",
            )}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-mono text-base font-bold tracking-[0.12em] text-foreground">
                {p.defect.toUpperCase()} · {p.location.toUpperCase()}
              </h2>
              <LevelBadge level={p.level} />
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{p.summary}</p>

            <div className="mt-4 grid grid-cols-3 gap-3">
              <div className="rounded-sm border border-border bg-surface-2 p-3">
                <div className="label-caps">Số lần xuất hiện</div>
                <div className="font-mono text-3xl font-bold text-destructive tabular-nums">
                  {p.occurrences}
                </div>
              </div>
              <div className="rounded-sm border border-border bg-surface-2 p-3">
                <div className="label-caps">Cửa sổ (số xe)</div>
                <div className="font-mono text-3xl font-bold text-foreground tabular-nums">
                  {p.window}
                </div>
              </div>
              <div className="rounded-sm border border-border bg-surface-2 p-3">
                <div className="label-caps">Xu hướng</div>
                {/* Backend does not expose a trend direction field — presence of an active alert
                    already implies an increasing pattern within the window, shown generically. */}
                <div className="flex items-center gap-1 font-mono text-lg font-bold text-destructive">
                  <TrendingUp className="size-4" />
                  Đang hoạt động
                </div>
              </div>
            </div>

            <div className="mt-3">
              <div className="label-caps">Xe bị ảnh hưởng</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {p.vehicles.map((v) => (
                  <span
                    key={v}
                    className="rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-foreground"
                  >
                    {v}
                  </span>
                ))}
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <Link
                to="/history"
                className="inline-flex items-center gap-1.5 rounded-sm border border-border px-2.5 py-1.5 font-mono text-[11px] tracking-[0.12em] text-muted-foreground transition-colors hover:border-info/45 hover:text-info"
              >
                <Search className="size-3.5" /> XEM CÁC XE BỊ ẢNH HƯỞNG
              </Link>
              <button
                disabled
                title="Chưa nối với backend"
                className="inline-flex items-center gap-1.5 rounded-sm border border-border px-2.5 py-1.5 font-mono text-[11px] tracking-[0.12em] text-muted-foreground opacity-60"
              >
                <Images className="size-3.5" /> XEM ẢNH LỖI
              </button>
              <button
                onClick={() => setInvestigating((prev) => [...new Set([...prev, p.id])])}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1.5 font-mono text-[11px] tracking-[0.12em] transition-colors",
                  investigating.includes(p.id)
                    ? "border-warning/50 bg-warning/10 text-warning"
                    : "border-border text-muted-foreground hover:border-warning/45 hover:text-warning",
                )}
              >
                <Wrench className="size-3.5" />
                {investigating.includes(p.id) ? "ĐANG XỬ LÝ" : "ĐÁNH DẤU ĐANG XỬ LÝ"}
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
