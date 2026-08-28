import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Activity,
  Bell,
  Camera,
  Gauge,
  History,
  LogOut,
  ScanSearch,
  ShieldAlert,
  UserRound,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Dot } from "./primitives";
import { profileDisplayName, useAuth } from "@/lib/auth";
import { useAgentRuns, useAgentStatus, useQualityAlerts } from "@/lib/queries";
import { IdentityPanel } from "./IdentityPanel";

const nav = [
  { to: "/", label: "Tổng quan ca", sub: "SHIFT OVERVIEW", icon: Gauge },
  { to: "/inspection", label: "Inspection", sub: "LIVE STATION", icon: ScanSearch },
  { to: "/hitl", label: "Hàng đợi HITL", sub: "HUMAN REVIEW", icon: Users },
  { to: "/warnings", label: "Cảnh báo realtime", sub: "EARLY WARNING", icon: ShieldAlert },
  { to: "/history", label: "Lịch sử inspection", sub: "AUDIT LOG", icon: History },
] as const;

const KNOWN_CAMERA_IDS = ["CAM-01", "CAM-02", "CAM-03", "CAM-04", "CAM-05"];

const ROLE_LABEL: Record<string, string> = {
  QC_SUPERVISOR: "Giám sát QC",
  QC_OPERATOR: "Vận hành QC",
};

function useClock() {
  const [now, setNow] = useState<string | null>(null);
  useEffect(() => {
    const tick = () =>
      setNow(
        new Date().toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }),
      );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function NotificationBell({
  warningCount,
  alerts,
}: {
  warningCount: number;
  alerts: { id: string; text: string }[];
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative grid size-9 place-items-center rounded-sm border border-border text-muted-foreground transition-colors hover:text-foreground"
      >
        <Bell className="size-4" />
        {warningCount > 0 ? (
          <span className="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full bg-warning font-mono text-[10px] font-bold text-warning-foreground">
            {warningCount}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 top-full z-30 mt-2 w-80 rounded-sm border border-border bg-surface shadow-lg">
          <div className="border-b border-border px-3 py-2 label-caps">
            Cảnh báo chất lượng ({warningCount})
          </div>
          <ul className="max-h-72 overflow-auto">
            {alerts.length === 0 ? (
              <li className="px-3 py-4 text-center text-sm text-muted-foreground">
                Không có cảnh báo nào đang hoạt động.
              </li>
            ) : (
              alerts.map((a) => (
                <li
                  key={a.id}
                  className="border-b border-border px-3 py-2 text-sm text-foreground last:border-b-0"
                >
                  {a.text}
                </li>
              ))
            )}
          </ul>
          <button
            onClick={() => {
              setOpen(false);
              void navigate({ to: "/warnings" });
            }}
            className="w-full border-t border-border px-3 py-2 text-center font-mono text-[11px] tracking-[0.12em] text-info hover:bg-info/10"
          >
            XEM TẤT CẢ CẢNH BÁO
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function QcShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const clock = useClock();
  const { profile, logout } = useAuth();
  const { data: agentStatus } = useAgentStatus();
  const { data: runs } = useAgentRuns();
  const { data: alertSummary } = useQualityAlerts();

  // A case with human_decision set has already left the operator's queue (it's now waiting on
  // a supervisor) — see frontend/src/routes/hitl.tsx's dedupeInterrupted for the same rule.
  const hitlPending =
    runs?.filter((r) => r.status === "INTERRUPTED" && !r.state.human_decision).length ?? 0;
  const alerts = alertSummary?.alerts ?? [];
  // WATCH alerts are an early, low-urgency signal (see /warnings) — they don't belong in the
  // "needs attention now" badge/bell count, only WARNING/CRITICAL do.
  const activeAlerts = alerts.filter((a) => a.severity !== "WATCH");
  const warningCount = activeAlerts.length;
  const engineOnline = agentStatus?.langgraph === "READY";
  const badgeByPath: Record<string, number> = { "/hitl": hitlPending, "/warnings": warningCount };

  const latestRun = runs?.[0];
  const usedCameras = new Set((latestRun?.state.camera_evidence ?? []).map((e) => e.camera_id));
  const initials = profileDisplayName(profile).slice(0, 2).toUpperCase();
  const currentNav = nav.find((item) => item.to === pathname);

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-[248px] shrink-0 flex-col border-r border-border bg-surface/90 backdrop-blur">
        <div className="flex items-center gap-3 border-b border-border px-4 py-4">
          <div className="grid size-9 place-items-center rounded-sm border border-info/40 bg-info/10 text-info">
            <Activity className="size-5" />
          </div>
          <div>
            <div className="font-mono text-sm font-bold tracking-[0.22em] text-foreground">
              AUTO QC
            </div>
            <div className="label-caps">Surface Vision AI</div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-2">
          {nav.map((item) => {
            const active = pathname === item.to;
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "group flex items-center gap-3 rounded-sm border border-transparent px-3 py-2.5 transition-colors",
                  active
                    ? "border-info/40 bg-info/10 text-foreground"
                    : "text-muted-foreground hover:bg-surface-2 hover:text-foreground",
                )}
              >
                <Icon className={cn("size-4 shrink-0", active && "text-info")} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{item.label}</span>
                  <span className="label-caps block truncate">{item.sub}</span>
                </span>
                {badgeByPath[item.to] ? (
                  <span className="rounded-sm border border-warning/40 bg-warning/10 px-1.5 font-mono text-[11px] text-warning">
                    {badgeByPath[item.to]}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="space-y-3 border-t border-border p-4">
          <div className="space-y-1.5 rounded-sm border border-border bg-surface-2 p-2.5">
            <div className="flex items-center justify-between">
              <span className="label-caps">AI Engine</span>
              <span
                className={cn(
                  "flex items-center gap-2 font-mono text-[11px]",
                  engineOnline ? "text-success" : "text-destructive",
                )}
              >
                <Dot state={engineOnline ? "ok" : "down"} /> {engineOnline ? "ONLINE" : "OFFLINE"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="label-caps">Camera</span>
              <span className="flex items-center gap-2 font-mono text-[11px] text-success">
                <Camera className="size-3" /> {usedCameras.size}/{KNOWN_CAMERA_IDS.length} ĐÃ CHỤP
              </span>
            </div>
          </div>
          <div className="flex min-w-0 items-center gap-2.5 rounded-sm border border-border bg-surface-2 p-3">
            <div className="grid size-7 shrink-0 place-items-center rounded-full border border-border bg-surface text-muted-foreground">
              <UserRound className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{profileDisplayName(profile)}</div>
              <div className="truncate text-[11px] text-muted-foreground">
                {profile ? (ROLE_LABEL[profile.role] ?? profile.role) : "Chưa xác thực"}
                {profile?.station_id ? ` · Trạm ${profile.station_id}` : ""}
              </div>
            </div>
          </div>
          <IdentityPanel />
          <Link
            to="/supervisor"
            className="block text-center text-[11px] text-info hover:underline"
          >
            → Chuyển sang giao diện QC Supervisor
          </Link>
          <button
            onClick={logout}
            className="flex w-full items-center justify-center gap-2 rounded-sm border border-border px-3 py-2 font-mono text-[11px] tracking-[0.14em] text-muted-foreground transition-colors hover:border-destructive/50 hover:text-destructive"
          >
            <LogOut className="size-3.5" /> ĐĂNG XUẤT
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-4 border-b border-border bg-background/85 px-6 py-3 backdrop-blur">
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold tracking-wide text-foreground">
              {currentNav?.label ?? "AUTO QC"}
            </h1>
            <div className="label-caps">{currentNav?.sub ?? "SURFACE VISION AI"}</div>
          </div>
          <div className="ml-auto flex items-center gap-4">
            <div
              className={cn(
                "hidden items-center gap-2 rounded-sm border px-2.5 py-1 font-mono text-[11px] tracking-[0.14em] lg:flex",
                engineOnline
                  ? "border-success/40 bg-success/10 text-success"
                  : "border-destructive/40 bg-destructive/10 text-destructive",
              )}
            >
              <Dot state={engineOnline ? "ok" : "down"} />{" "}
              {engineOnline ? "HỆ THỐNG BÌNH THƯỜNG" : "MẤT KẾT NỐI BACKEND"}
            </div>
            <div className="text-right">
              <div className="font-mono text-lg leading-none tabular-nums text-foreground">
                {clock ?? "--:--:--"}
              </div>
              <div className="label-caps">Giờ địa phương</div>
            </div>
            <NotificationBell
              warningCount={warningCount}
              alerts={activeAlerts.map((a) => ({ id: a.id, text: a.message_vi || a.message_en }))}
            />
            <div className="grid size-9 place-items-center rounded-full border border-info/40 bg-info/10 font-mono text-xs text-info">
              {initials}
            </div>
          </div>
        </header>
        <main className="min-w-0 flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
