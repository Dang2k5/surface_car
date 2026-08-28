import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import { useMemo, useState } from "react";
import { CheckSquare, Images, Search, Square, TrendingUp, Wrench } from "lucide-react";
import type { WarningLevel } from "@/lib/qc-data";
import { LevelBadge, Panel } from "@/components/qc/primitives";
import { cn } from "@/lib/utils";
import { useQualityAlerts } from "@/lib/queries";
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
  return severity;
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
          "Realtime detection of repeated surface defect patterns across consecutive vehicles with severity levels and an inspector action checklist.",
      },
      { property: "og:title", content: "Early Defect Warning — AUTO QC Station 03" },
      {
        property: "og:description",
        content:
          "Repeated defect pattern detection with an immediate inspector checklist and escalation actions.",
      },
    ],
  }),
  component: EarlyWarnings,
});

function EarlyWarnings() {
  const { data: alertSummary, isLoading, isError } = useQualityAlerts();
  const [investigating, setInvestigating] = useState<string[]>([]);
  const [checkedItems, setCheckedItems] = useState<Set<string>>(new Set());

  const alerts = useMemo(() => alertSummary?.alerts ?? [], [alertSummary]);
  const patterns = useMemo(() => alerts.map(toPattern), [alerts]);
  const criticalCount = patterns.filter((p) => p.level === "CRITICAL").length;
  // WATCH is an early, low-urgency signal (worth tracking in the level breakdown) — it does not
  // belong in the inspector's "check right now" list, which should only ever hold things that
  // actually warrant an immediate action at the station.
  const immediateAlerts = useMemo(
    () => alerts.filter((a) => a.severity !== "WATCH" && a.upstream_checks_vi.length > 0),
    [alerts],
  );
  const levelCounts = useMemo(() => {
    const counts: Record<WarningLevel, number> = { WATCH: 0, WARNING: 0, CRITICAL: 0 };
    for (const p of patterns) counts[p.level] += 1;
    return counts;
  }, [patterns]);

  function toggleCheck(key: string) {
    setCheckedItems((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

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
          title="Việc cần kiểm tra ngay"
          right={<span className="label-caps">inspector</span>}
        >
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Đang tải cảnh báo chất lượng…</p>
          ) : immediateAlerts.length === 0 ? (
            <div className="flex h-[200px] items-center justify-center px-4 text-center text-sm text-muted-foreground">
              Không có việc kiểm tra nào cần thực hiện lúc này.
            </div>
          ) : (
            <div className="max-h-[420px] space-y-4 overflow-y-auto pr-1">
              {immediateAlerts.map((alert) => (
                  <div key={alert.id} className="rounded-sm border border-border bg-surface-2 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs font-bold tracking-[0.1em] text-foreground">
                        {alert.defect_type.toUpperCase()} · {alert.zone_name.toUpperCase()} ·{" "}
                        {alert.camera_id}
                      </span>
                      <LevelBadge level={levelFromSeverity(alert.severity)} />
                    </div>
                    <ul className="mt-2 space-y-1.5">
                      {alert.upstream_checks_vi.map((check, i) => {
                        const key = `${alert.id}:${i}`;
                        const checked = checkedItems.has(key);
                        return (
                          <li key={key}>
                            <button
                              type="button"
                              onClick={() => toggleCheck(key)}
                              className={cn(
                                "flex w-full items-start gap-2 rounded-sm border border-transparent px-1.5 py-1 text-left text-sm transition-colors hover:border-border",
                                checked
                                  ? "text-muted-foreground line-through"
                                  : "text-foreground",
                              )}
                            >
                              {checked ? (
                                <CheckSquare className="mt-0.5 size-4 shrink-0 text-info" />
                              ) : (
                                <Square className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                              )}
                              {check}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
            </div>
          )}
        </Panel>

        <Panel title="Ngưỡng mức độ cảnh báo">
          <div className="grid grid-cols-3 gap-2">
            {(["WATCH", "WARNING", "CRITICAL"] as const).map((lvl, i) => (
              <div
                key={lvl}
                className={cn(
                  "rounded-sm border bg-surface-2 p-3 text-center",
                  i === 2 && "border-destructive/45",
                  i === 1 && "border-warning/45",
                  i === 0 && "border-info/40",
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
