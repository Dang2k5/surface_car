// Client-side aggregation for the QC_SUPERVISOR console. The backend has no per-station/per-hour
// breakdown endpoint, so charts that need that shape are derived here from data the real endpoints
// already return (GET /api/trend, GET /agent/runs) instead of being fabricated.
import type { GraphRun, TrendRow } from "./api-types";
import type { TrendPoint } from "@/components/supervisor/charts";

export function trendToPoints(rows: TrendRow[]): TrendPoint[] {
  return rows.map((r) => ({
    t: r.group_value,
    pass: r.pass_count,
    fail: r.fail_count,
    defectRate: r.total_inspections
      ? Math.round((r.fail_count / r.total_inspections) * 1000) / 10
      : 0,
  }));
}

const DEFECT_COLORS: Record<string, string> = {
  scratch: "var(--destructive)",
  dent: "var(--warning)",
};
const FALLBACK_COLORS = ["var(--info)", "var(--success)", "var(--chart-5)"];

export function defectMixFromRuns(runs: GraphRun[]) {
  const counts = new Map<string, number>();
  for (const run of runs) {
    for (const result of run.state.camera_results ?? []) {
      for (const d of result.detections ?? []) {
        counts.set(d.class_name, (counts.get(d.class_name) ?? 0) + 1);
      }
    }
    if (!run.state.camera_results?.length && run.state.defect_type) {
      counts.set(run.state.defect_type, (counts.get(run.state.defect_type) ?? 0) + 1);
    }
  }
  let fallbackIdx = 0;
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({
      name,
      value,
      color:
        DEFECT_COLORS[name] ??
        FALLBACK_COLORS[fallbackIdx++ % FALLBACK_COLORS.length] ??
        "var(--muted-foreground)",
    }));
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: "var(--destructive)",
  major: "var(--warning)",
  minor: "var(--info)",
};

export function severityMixFromRuns(runs: GraphRun[]) {
  const counts = new Map<string, number>();
  for (const run of runs) {
    let hasDetections = false;
    for (const result of run.state.camera_results ?? []) {
      for (const d of result.detections ?? []) {
        hasDetections = true;
        const key = (d.severity_rank || "unassessed").toLowerCase();
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
    }
    if (!hasDetections && run.state.severity) {
      const key = run.state.severity.toLowerCase();
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1),
      value,
      color: SEVERITY_COLORS[name] ?? "var(--muted-foreground)",
    }));
}

/** Most recent run per vehicle_id — GET /agent/runs is ordered updated_at DESC but not deduped. */
export function dedupeByVehicle(runs: GraphRun[]): GraphRun[] {
  const seen = new Set<string>();
  const result: GraphRun[] = [];
  for (const r of runs) {
    if (seen.has(r.state.vehicle_id)) continue;
    seen.add(r.state.vehicle_id);
    result.push(r);
  }
  return result;
}
