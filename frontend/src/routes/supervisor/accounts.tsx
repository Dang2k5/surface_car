import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Lock, Unlock } from "lucide-react";
import { Badge, Btn, EmptyState, PageHeader, Panel } from "@/components/supervisor/ui";
import { useAuth } from "@/lib/auth";
import { useProfiles, useStations, useUpdateProfile } from "@/lib/queries";
import { cn } from "@/lib/utils";
import type { Profile, Role, Station } from "@/lib/api-types";

export const Route = createFileRoute("/supervisor/accounts")({
  head: () => ({
    meta: [{ title: "Quản lý tài khoản theo trạm — QC Supervisor" }],
  }),
  component: Accounts,
});

const UNASSIGNED = "__unassigned__";

const moveSelectClass =
  "h-7 min-w-0 rounded-sm border border-border bg-surface-2 px-1.5 text-[11px] text-foreground outline-none focus:border-ring disabled:opacity-50";

/** SQLite returns 0/1 where Postgres returns a boolean; a row provisioned before the column
 * existed has neither, and predates deactivation entirely — so it counts as active. */
function isProfileActive(p: Profile): boolean {
  return p.active === undefined || p.active === true || p.active === 1;
}

function AccountRow({
  profile: p,
  isSelf,
  stations,
  stationId,
  busy,
  onMove,
  onChangeRole,
  onToggleActive,
}: {
  profile: Profile;
  isSelf: boolean;
  stations: Station[];
  /** The station this row is listed under, or null in the unassigned panel. */
  stationId: string | null;
  busy: boolean;
  onMove: (p: Profile, stationId: string) => void;
  onChangeRole: (p: Profile, role: Role) => void;
  onToggleActive: (p: Profile, active: boolean) => void;
}) {
  const active = isProfileActive(p);
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 border-b border-border/60 px-3 py-2 last:border-b-0",
        !active && "opacity-60",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12.5px] font-medium text-foreground">
          {p.full_name || p.email || p.user_id}
          {isSelf ? <span className="ml-1.5 text-muted-foreground">(bạn)</span> : null}
        </div>
        {!active ? (
          <Badge tone="warn" className="mt-1">
            Đã khóa
          </Badge>
        ) : null}
      </div>
      <div className="flex items-center gap-1.5">
        <select
          value={p.role === "QC_SUPERVISOR" ? "QC_SUPERVISOR" : "QC_OPERATOR"}
          onChange={(e) => onChangeRole(p, e.target.value as Role)}
          disabled={isSelf || busy}
          title={isSelf ? "Không thể tự thay đổi vai trò của chính mình" : "Đổi vai trò"}
          className={moveSelectClass}
        >
          <option value="QC_OPERATOR">QC_OPERATOR</option>
          <option value="QC_SUPERVISOR">QC_SUPERVISOR</option>
        </select>
        {stationId === null ? (
          <select
            value=""
            onChange={(e) => e.target.value && onMove(p, e.target.value)}
            disabled={busy}
            className={moveSelectClass}
          >
            <option value="">Gán vào trạm…</option>
            {stations.map((s) => (
              <option key={s.station_id} value={s.station_id}>
                {s.name}
              </option>
            ))}
          </select>
        ) : (
          <select
            value={stationId}
            onChange={(e) => onMove(p, e.target.value === UNASSIGNED ? "" : e.target.value)}
            disabled={busy}
            title="Chuyển sang trạm khác"
            className={moveSelectClass}
          >
            <option value={UNASSIGNED}>— Bỏ gán —</option>
            {stations.map((opt) => (
              <option key={opt.station_id} value={opt.station_id}>
                {opt.name}
              </option>
            ))}
          </select>
        )}
        <Btn
          variant={active ? "danger" : "success"}
          size="xs"
          disabled={isSelf || busy}
          onClick={() => onToggleActive(p, !active)}
          title={
            isSelf
              ? "Không thể tự khóa tài khoản của chính mình"
              : active
                ? "Khóa tài khoản — chặn mọi truy cập API"
                : "Mở khóa tài khoản"
          }
        >
          {active ? <Lock className="size-3" /> : <Unlock className="size-3" />}
          {active ? "Khóa" : "Mở"}
        </Btn>
      </div>
    </div>
  );
}

function Accounts() {
  const { profile: currentProfile } = useAuth();
  const profilesQuery = useProfiles();
  const stationsQuery = useStations(false);
  const updateProfile = useUpdateProfile();
  const [error, setError] = useState("");
  const [movingId, setMovingId] = useState<string | null>(null);

  const profiles = profilesQuery.data ?? [];
  const stations = stationsQuery.data ?? [];

  const grouped = useMemo(() => {
    const byStation = new Map<string, Profile[]>();
    byStation.set(UNASSIGNED, []);
    for (const s of stations) byStation.set(s.station_id, []);
    for (const p of profiles) {
      const key = p.station_id && byStation.has(p.station_id) ? p.station_id : UNASSIGNED;
      byStation.get(key)!.push(p);
    }
    return byStation;
  }, [profiles, stations]);

  async function patch(p: Profile, payload: Parameters<typeof updateProfile.mutateAsync>[0]["payload"], failure: string) {
    setError("");
    setMovingId(p.user_id);
    try {
      await updateProfile.mutateAsync({ userId: p.user_id, payload });
    } catch (err) {
      setError(err instanceof Error ? err.message : failure);
    } finally {
      setMovingId(null);
    }
  }

  const move = (p: Profile, stationId: string) =>
    void patch(p, { station_id: stationId || null }, "Chuyển trạm thất bại.");
  const changeRole = (p: Profile, role: Role) =>
    void patch(p, { role }, "Đổi vai trò thất bại.");
  const toggleActive = (p: Profile, active: boolean) =>
    void patch(p, { active }, active ? "Mở khóa thất bại." : "Khóa tài khoản thất bại.");

  const unassignedCount = grouped.get(UNASSIGNED)?.length ?? 0;
  const lockedCount = profiles.filter((p) => !isProfileActive(p)).length;

  if (profilesQuery.isPending || stationsQuery.isPending) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        Đang tải…
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Quản lý tài khoản theo trạm"
        meta={[
          { label: "Tổng tài khoản", value: String(profiles.length) },
          { label: "Số trạm", value: String(stations.length) },
          { label: "Chưa gán trạm", value: String(unassignedCount) },
          { label: "Đã khóa", value: String(lockedCount) },
        ]}
      />

      {error ? <p className="text-[11px] text-destructive">{error}</p> : null}

      {profiles.length === 0 ? (
        <Panel dense>
          <EmptyState
            title="Chưa có tài khoản nào"
            description="Tài khoản sẽ xuất hiện ở đây sau lần đăng nhập đầu tiên."
          />
        </Panel>
      ) : stations.length === 0 ? (
        <Panel dense>
          <EmptyState
            title="Chưa có trạm QC nào"
            description="Tạo trạm ở mục Ca, Lô & Trạm QC trước khi gán tài khoản vào trạm."
          />
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {/* Accounts land here only when sign-up carried no station, or the station it named
           * no longer exists — the form at /login now asks for one up front. */}
          {unassignedCount > 0 && (
            <Panel
              className="lg:col-span-2 xl:col-span-3"
              title="Chưa gán trạm"
              actions={<Badge tone="warn">{unassignedCount}</Badge>}
              dense
            >
              {grouped.get(UNASSIGNED)!.map((p) => (
                <AccountRow
                  key={p.user_id}
                  profile={p}
                  isSelf={p.user_id === currentProfile?.user_id}
                  stations={stations}
                  stationId={null}
                  busy={movingId === p.user_id}
                  onMove={move}
                  onChangeRole={changeRole}
                  onToggleActive={toggleActive}
                />
              ))}
            </Panel>
          )}

          {stations.map((s) => {
            const members = grouped.get(s.station_id) ?? [];
            return (
              <Panel
                key={s.station_id}
                title={s.name}
                subtitle={s.station_id}
                actions={<Badge tone={members.length ? "pass" : "neutral"}>{members.length}</Badge>}
                dense
              >
                {members.length === 0 ? (
                  <div className="px-3 py-4 text-[11.5px] text-muted-foreground">
                    Chưa có ai phụ trách trạm này.
                  </div>
                ) : (
                  members.map((p) => (
                    <AccountRow
                      key={p.user_id}
                      profile={p}
                      isSelf={p.user_id === currentProfile?.user_id}
                      stations={stations}
                      stationId={s.station_id}
                      busy={movingId === p.user_id}
                      onMove={move}
                      onChangeRole={changeRole}
                      onToggleActive={toggleActive}
                    />
                  ))
                )}
              </Panel>
            );
          })}
        </div>
      )}
    </div>
  );
}
