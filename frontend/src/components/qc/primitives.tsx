import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { Verdict, WarningLevel } from "@/lib/qc-data";

export function Panel({
  title,
  right,
  children,
  className,
  bodyClassName,
}: {
  title?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("panel flex min-h-0 flex-col", className)}>
      {title ? (
        <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
          <h2 className="label-caps text-foreground/80">{title}</h2>
          {right}
        </header>
      ) : null}
      <div className={cn("min-h-0 flex-1 p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Dot({
  state = "ok",
  pulse = true,
}: {
  state?: "ok" | "warn" | "down" | "info";
  pulse?: boolean;
}) {
  const color =
    state === "ok"
      ? "bg-success"
      : state === "warn"
        ? "bg-warning"
        : state === "down"
          ? "bg-destructive"
          : "bg-info";
  return (
    <span
      className={cn("inline-block size-2 shrink-0 rounded-full", color, pulse && "live-dot")}
      aria-hidden
    />
  );
}

export function Field({
  label,
  value,
  mono = true,
  tone,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
  tone?: "success" | "warning" | "danger" | "info";
}) {
  const toneClass =
    tone === "success"
      ? "text-success"
      : tone === "warning"
        ? "text-warning"
        : tone === "danger"
          ? "text-destructive"
          : tone === "info"
            ? "text-info"
            : "text-foreground";
  return (
    <div className="min-w-0">
      <div className="label-caps">{label}</div>
      <div className={cn("truncate text-sm", mono && "font-mono", toneClass)}>{value}</div>
    </div>
  );
}

export function VerdictBadge({
  verdict,
  size = "sm",
}: {
  verdict: Verdict;
  size?: "sm" | "lg" | "xl";
}) {
  const map: Record<Verdict, string> = {
    PASS: "text-success border-success/40 bg-success/10",
    FAIL: "text-destructive border-destructive/40 bg-destructive/10",
    HITL: "text-warning border-warning/40 bg-warning/10",
  };
  const sizes = {
    sm: "px-2 py-0.5 text-[11px]",
    lg: "px-3 py-1 text-sm",
    xl: "px-4 py-2 text-2xl",
  } as const;
  const label = verdict === "HITL" ? "HITL" : verdict;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-sm border font-mono font-semibold tracking-[0.12em]",
        map[verdict],
        sizes[size],
      )}
    >
      {label}
    </span>
  );
}

export function LevelBadge({ level }: { level: WarningLevel }) {
  const map: Record<WarningLevel, string> = {
    WATCH: "text-info border-info/40 bg-info/10",
    WARNING: "text-warning border-warning/40 bg-warning/10",
    CRITICAL: "text-destructive border-destructive/40 bg-destructive/10 glow-danger",
  };
  return (
    <span
      className={cn(
        "inline-flex rounded-sm border px-2 py-0.5 font-mono text-[11px] font-semibold tracking-[0.12em]",
        map[level],
      )}
    >
      {level}
    </span>
  );
}

export function Meter({
  value,
  tone = "info",
}: {
  value: number;
  tone?: "info" | "success" | "warning" | "danger";
}) {
  const bg =
    tone === "success"
      ? "bg-success"
      : tone === "warning"
        ? "bg-warning"
        : tone === "danger"
          ? "bg-destructive"
          : "bg-info";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className={cn("h-full rounded-full", bg)} style={{ width: `${value}%` }} />
    </div>
  );
}
