import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/* ----------------------------------------------------------- Panel */

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
  dense,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
  dense?: boolean;
}) {
  return (
    <section className={cn("panel flex min-w-0 flex-col", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
          <div className="min-w-0">
            {title && (
              <h2 className="truncate text-[14px] font-semibold tracking-tight">{title}</h2>
            )}
            {subtitle && (
              <p className="mt-0.5 truncate text-[12px] text-muted-foreground">{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={cn(dense ? "" : "p-4", "min-w-0 flex-1", bodyClassName)}>{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------ Badges */

export type Tone = "pass" | "fail" | "warn" | "info" | "neutral";

const toneMap: Record<Tone, string> = {
  pass: "text-success bg-success/10 border-success/35",
  fail: "text-destructive bg-destructive/10 border-destructive/35",
  warn: "text-warning bg-warning/10 border-warning/35",
  info: "text-info bg-info/10 border-info/35",
  neutral: "text-muted-foreground bg-surface-2 border-border",
};

export function Badge({
  tone = "neutral",
  children,
  className,
  dot,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm border px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.07em]",
        toneMap[tone],
        className,
      )}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function severityTone(s: string): Tone {
  const v = s.toLowerCase();
  if (v === "critical") return "fail";
  if (v === "major" || v === "warning" || v === "high") return "warn";
  if (v === "minor" || v === "low") return "info";
  return "neutral";
}

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <Badge tone={severityTone(severity)} dot>
      {severity}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const v = status.toUpperCase();
  const tone: Tone =
    v === "PASS" ||
    v === "HEALTHY" ||
    v === "RESOLVED" ||
    v === "ACTIVE" ||
    v === "COMPLETED" ||
    v === "APPROVED"
      ? "pass"
      : v === "FAIL" || v === "OFFLINE" || v === "OVERDUE" || v === "REJECT"
        ? "fail"
        : v === "WARNING" || v === "PENDING" || v === "SCHEDULED" || v === "DRAFT"
          ? "warn"
          : v === "ESCALATED" || v === "ASSIGNED" || v === "INVESTIGATING" || v === "INTERRUPTED"
            ? "info"
            : "neutral";
  return <Badge tone={tone}>{status}</Badge>;
}

/* ------------------------------------------------------------ Buttons */

export function Btn({
  children,
  variant = "ghost",
  size = "sm",
  className,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "ghost" | "solid" | "outline" | "danger" | "success";
  size?: "sm" | "xs";
}) {
  return (
    <button
      {...rest}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-sm border font-medium transition-colors disabled:opacity-45",
        size === "xs" ? "h-6 px-2 text-[12px]" : "h-7 px-2.5 text-xs",
        variant === "ghost" &&
          "border-transparent text-muted-foreground hover:bg-surface-2 hover:text-foreground",
        variant === "outline" &&
          "border-border bg-surface-2 text-foreground hover:border-border-strong hover:bg-surface-2",
        variant === "solid" && "border-info/50 bg-info/20 text-info hover:bg-info/30",
        variant === "danger" &&
          "border-destructive/45 bg-destructive/10 text-destructive hover:bg-destructive/20",
        variant === "success" && "border-success/45 bg-success/10 text-success hover:bg-success/20",
        className,
      )}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------ KPI card */

export function KpiCard({
  label,
  value,
  sub,
  tone = "neutral",
  to,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
  to?: string;
}) {
  const accent =
    tone === "pass"
      ? "before:bg-success"
      : tone === "fail"
        ? "before:bg-destructive"
        : tone === "warn"
          ? "before:bg-warning"
          : tone === "info"
            ? "before:bg-info"
            : "before:bg-border-strong";

  const body = (
    <div
      className={cn(
        "panel relative overflow-hidden p-3.5 transition-colors hover:border-border-strong",
        "before:absolute before:inset-y-0 before:left-0 before:w-[2px] before:content-['']",
        accent,
      )}
    >
      <div className="label-caps">{label}</div>
      <div className="num mt-2 text-[26px] font-semibold leading-none">{value}</div>
      {sub && <div className="mt-2 truncate text-[12px] text-muted-foreground">{sub}</div>}
    </div>
  );

  if (!to) return body;
  return (
    <Link to={to as never} className="block">
      {body}
    </Link>
  );
}

/* ------------------------------------------------------------- Table */

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className="min-w-0 overflow-x-auto">
      <table className={cn("w-full border-collapse text-[13px]", className)}>{children}</table>
    </div>
  );
}

export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <th
      className={cn(
        "sticky top-0 z-10 whitespace-nowrap border-b border-border bg-surface px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <td
      className={cn(
        "whitespace-nowrap border-b border-border/60 px-3 py-2 align-middle",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function Tr({
  children,
  onClick,
  active,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  active?: boolean;
  className?: string;
}) {
  return (
    <tr
      onClick={onClick}
      className={cn(
        onClick && "cursor-pointer",
        "transition-colors hover:bg-surface-2",
        active && "bg-surface-2",
        className,
      )}
    >
      {children}
    </tr>
  );
}

/* ------------------------------------------------------------ Filters */

export function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="label-caps">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-7 min-w-0 rounded-sm border border-border bg-surface-2 px-2 text-[13px] text-foreground outline-none focus:border-ring"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function TextField({
  label,
  value,
  onChange,
  placeholder,
  mono,
  type = "text",
  list,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
  type?: "text" | "date";
  list?: string;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="label-caps">{label}</span>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        list={list}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "h-7 min-w-0 rounded-sm border border-border bg-surface-2 px-2 text-[13px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-ring",
          mono && "font-mono",
        )}
      />
    </label>
  );
}

export function TextArea({
  label,
  value,
  onChange,
  placeholder,
  rows = 3,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  hint?: string;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="label-caps">{label}</span>
      <textarea
        value={value}
        placeholder={placeholder}
        rows={rows}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-0 resize-y rounded-sm border border-border bg-surface-2 px-2 py-1.5 text-[13px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-ring"
      />
      {hint && <span className="text-[11.5px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

export function Checkbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-[13px] text-foreground">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-3.5 rounded-[2px] border-border accent-info"
      />
      {label}
    </label>
  );
}

export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { key: T; label: string }[];
}) {
  return (
    <div className="inline-flex rounded-sm border border-border bg-surface-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={cn(
            "rounded-[2px] px-2.5 py-1 text-[12px] font-medium transition-colors",
            value === o.key
              ? "bg-surface text-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------ Timeline */

const kindTone: Record<string, Tone> = {
  production: "info",
  camera: "warn",
  rule: "info",
  defect: "fail",
  human: "pass",
};

export function Timeline({ items }: { items: { t: string; text: string; kind?: string }[] }) {
  return (
    <ol className="relative ml-1 border-l border-border pl-4">
      {items.map((it, i) => {
        const tone = kindTone[it.kind ?? ""] ?? "neutral";
        return (
          <li key={i} className="relative pb-4 last:pb-0">
            <span
              className={cn(
                "absolute -left-[21px] top-1 size-2 rounded-full ring-4 ring-surface",
                tone === "fail" && "bg-destructive",
                tone === "warn" && "bg-warning",
                tone === "info" && "bg-info",
                tone === "pass" && "bg-success",
                tone === "neutral" && "bg-border-strong",
              )}
            />
            <div className="num text-[12px] text-muted-foreground">{it.t}</div>
            <div className="mt-0.5 text-[13px] leading-snug text-foreground">{it.text}</div>
            {it.kind && <div className="label-caps mt-1">{it.kind}</div>}
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------- misc states */

export function EmptyState({
  title,
  description,
  tone = "pass",
  action,
}: {
  title: string;
  description: string;
  tone?: Tone;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <div
        className={cn(
          "mb-1 flex size-9 items-center justify-center rounded-sm border",
          toneMap[tone],
        )}
      >
        <span className="text-[14px]">✓</span>
      </div>
      <h3 className="text-[14px] font-semibold">{title}</h3>
      <p className="max-w-sm text-[13px] leading-relaxed text-muted-foreground">{description}</p>
      {action}
    </div>
  );
}

export function Field({
  label,
  children,
  mono,
}: {
  label: string;
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="label-caps">{label}</div>
      <div className={cn("mt-1 truncate text-[13.5px] text-foreground", mono && "num")}>
        {children}
      </div>
    </div>
  );
}

export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  children,
  width = "max-w-[880px]",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  width?: string;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-background/70 backdrop-blur-[2px]" onClick={onClose} />
      <aside
        className={cn(
          "relative flex h-full w-full flex-col border-l border-border-strong bg-surface shadow-2xl",
          width,
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-[15px] font-semibold">{title}</h2>
            {subtitle && (
              <div className="mt-0.5 truncate text-[12px] text-muted-foreground">{subtitle}</div>
            )}
          </div>
          <Btn variant="outline" onClick={onClose}>
            Đóng ✕
          </Btn>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
      </aside>
    </div>
  );
}

export function PageHeader({
  title,
  right,
  meta,
}: {
  title: string;
  right?: ReactNode;
  meta?: { label: string; value: string }[];
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-3">
      <div className="min-w-0">
        <h1 className="text-[21px] font-semibold tracking-tight">{title}</h1>
        {meta && (
          <div className="mt-2.5 flex flex-wrap items-center gap-x-5 gap-y-1">
            {meta.map((m) => (
              <div key={m.label} className="flex items-baseline gap-1.5">
                <span className="label-caps">{m.label}</span>
                <span className="num text-[13px] text-foreground">{m.value}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  );
}

export function Bar({ value, tone = "info" }: { value: number; tone?: Tone }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        className={cn(
          "h-full rounded-full",
          tone === "pass" && "bg-success",
          tone === "fail" && "bg-destructive",
          tone === "warn" && "bg-warning",
          tone === "info" && "bg-info",
          tone === "neutral" && "bg-border-strong",
        )}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}
