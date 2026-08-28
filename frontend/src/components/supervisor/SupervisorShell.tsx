import { Link, useRouterState } from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  CalendarClock,
  Cpu,
  Gauge,
  Inbox,
  LogOut,
  ScrollText,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { profileDisplayName, useAuth } from "@/lib/auth";
import { useAgentRuns, useAgentStatus, useQualityAlerts } from "@/lib/queries";
import { Dot } from "@/components/qc/primitives";

const NAV = [
  { to: "/supervisor", label: "Trung tâm điều hành", icon: Gauge, group: "Theo dõi" },
  {
    to: "/supervisor/anomalies",
    label: "Bất thường hệ thống",
    icon: AlertTriangle,
    group: "Điều tra",
    badgeKey: "anomalies",
  },
  {
    to: "/supervisor/escalations",
    label: "Hàng đợi leo thang",
    icon: Inbox,
    group: "Điều tra",
    badgeKey: "escalations",
  },
  { to: "/supervisor/inspections", label: "Tra cứu inspection", icon: Search, group: "Điều tra" },
  { to: "/supervisor/rules", label: "Chính sách QC", icon: SlidersHorizontal, group: "Quản trị" },
  {
    to: "/supervisor/catalogs",
    label: "Ca, Lô, Trạm & Danh mục lỗi",
    icon: CalendarClock,
    group: "Quản trị",
  },
  { to: "/supervisor/accounts", label: "Quản lý tài khoản", icon: Users, group: "Quản trị" },
  { to: "/supervisor/audit", label: "Nhật ký & Override", icon: ScrollText, group: "Quản trị" },
] as const;

function useClock() {
  const [now, setNow] = useState<string | null>(null);
  useEffect(() => {
    const tick = () => setNow(new Date().toTimeString().slice(0, 8));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function SupervisorShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const groups = ["Theo dõi", "Điều tra", "Quản trị"];
  const clock = useClock();
  const { profile, logout } = useAuth();
  const statusQuery = useAgentStatus();
  const runsQuery = useAgentRuns();
  const alertsQuery = useQualityAlerts();

  const engineOnline = statusQuery.data?.langgraph === "READY";
  // Only cases past the operator's own review (human_decision set) are actually waiting on a
  // supervisor — see frontend/src/routes/supervisor/escalations.tsx.
  const escalationsPending =
    runsQuery.data?.filter((r) => r.status === "INTERRUPTED" && r.state.human_decision).length ?? 0;
  const anomalyCount = alertsQuery.data?.alerts.length ?? 0;
  const badgeByKey: Record<string, number> = {
    escalations: escalationsPending,
    anomalies: anomalyCount,
  };

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-30 flex w-[248px] flex-col border-r border-border bg-surface">
        <div className="flex h-[52px] items-center gap-2.5 border-b border-border px-4">
          <div className="flex size-7 items-center justify-center rounded-sm border border-info/40 bg-info/15">
            <Cpu className="size-4 text-info" />
          </div>
          <div className="min-w-0">
            <div className="truncate font-mono text-[13px] font-bold tracking-[0.14em] text-foreground">
              QC SUPERVISOR
            </div>
            <div className="label-caps">Surface Vision AI</div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {groups.map((g) => (
            <div key={g} className="mb-4">
              <div className="label-caps px-2 pb-1.5">{g}</div>
              {NAV.filter((n) => n.group === g).map((item) => {
                const active =
                  item.to === "/supervisor"
                    ? pathname === "/supervisor"
                    : pathname.startsWith(item.to);
                const Icon = item.icon;
                const badge = "badgeKey" in item ? badgeByKey[item.badgeKey] : undefined;
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={cn(
                      "relative mb-0.5 flex items-center gap-2.5 rounded-sm px-2 py-[7px] text-[12.5px] transition-colors",
                      active
                        ? "bg-surface-2 font-medium text-foreground before:absolute before:inset-y-1 before:left-0 before:w-[2px] before:bg-info before:content-['']"
                        : "text-muted-foreground hover:bg-surface-2/60 hover:text-foreground",
                    )}
                  >
                    <Icon
                      className={cn(
                        "size-4 shrink-0",
                        active ? "text-info" : "text-muted-foreground",
                      )}
                    />
                    <span className="truncate">{item.label}</span>
                    {badge ? (
                      <span className="num ml-auto rounded-sm border border-warning/35 bg-warning/10 px-1 text-[10px] text-warning">
                        {badge}
                      </span>
                    ) : null}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="space-y-2 border-t border-border px-3 py-2.5">
          <div className="flex items-center justify-between">
            <span className="label-caps">AI Engine</span>
            <span
              className={cn(
                "flex items-center gap-1.5 font-mono text-[11px]",
                engineOnline ? "text-success" : "text-destructive",
              )}
            >
              <Dot state={engineOnline ? "ok" : "down"} /> {engineOnline ? "ONLINE" : "OFFLINE"}
            </span>
          </div>
          <div className="truncate text-[11.5px] font-medium text-foreground">
            {profileDisplayName(profile)}
          </div>
          <Link to="/" className="block text-[11px] text-info hover:underline">
            → Chuyển sang giao diện QC Inspector
          </Link>
          <button
            onClick={logout}
            className="flex w-full items-center justify-center gap-2 rounded-sm border border-border px-2.5 py-1.5 font-mono text-[10.5px] tracking-[0.12em] text-muted-foreground transition-colors hover:border-destructive/50 hover:text-destructive"
          >
            <LogOut className="size-3.5" /> ĐĂNG XUẤT
          </button>
        </div>
      </aside>

      <div className="ml-[248px] flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-[52px] items-center gap-3 border-b border-border bg-surface/95 px-4 backdrop-blur">
          <div
            className={cn(
              "flex items-center gap-1.5 rounded-sm border px-2.5 py-1 font-mono text-[11px] tracking-[0.1em]",
              engineOnline
                ? "border-success/40 bg-success/10 text-success"
                : "border-destructive/40 bg-destructive/10 text-destructive",
            )}
          >
            <ShieldCheck className="size-3.5" />{" "}
            {engineOnline ? "AI Inspect · Operational" : "AI Inspect · Offline"}
          </div>
          <div className="ml-auto flex items-center gap-4">
            <span className="hidden items-center gap-1.5 font-mono text-[12px] text-muted-foreground lg:flex">
              <Activity className="size-3.5" /> {clock ?? "--:--:--"}
            </span>
            <div className="flex size-7 items-center justify-center rounded-sm bg-info/20 font-mono text-[10px] font-bold text-info">
              {profileDisplayName(profile).slice(0, 2).toUpperCase()}
            </div>
          </div>
        </header>
        <main className="min-w-0 flex-1 p-4 xl:p-5">{children}</main>
      </div>
    </div>
  );
}
