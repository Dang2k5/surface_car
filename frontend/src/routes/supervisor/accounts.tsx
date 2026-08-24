import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Badge, EmptyState, PageHeader, Panel } from "@/components/supervisor/ui";
import { useAuth } from "@/lib/auth";
import { useProfiles, useStations, useUpdateProfile } from "@/lib/queries";
import type { Profile, Role } from "@/lib/api-types";

export const Route = createFileRoute("/supervisor/accounts")({
  head: () => ({
    meta: [{ title: "Quản lý tài khoản theo trạm — QC Supervisor" }],
  }),
  component: Accounts,
});

const UNASSIGNED = "__unassigned__";

const moveSelectClass =
  "h-7 min-w-0 rounded-sm border border-border bg-surface-2 px-1.5 text-[11px] text-foreground outline-none focus:border-ring";

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

  async function move(p: Profile, stationId: string) {
    setError("");
    setMovingId(p.user_id);
    try {
      await updateProfile.mutateAsync({
        userId: p.user_id,
        payload: { station_id: stationId || null },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chuyển trạm thất bại.");
    } finally {
      setMovingId(null);
    }
  }

  async function changeRole(p: Profile, role: Role) {
    setError("");
    setMovingId(p.user_id);
    try {
      await updateProfile.mutateAsync({ userId: p.user_id, payload: { role } });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đổi vai trò thất bại.");
    } finally {
      setMovingId(null);
    }
  }

  const unassignedCount = grouped.get(UNASSIGNED)?.length ?? 0;

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
        description="Mỗi inspector/supervisor thuộc một trạm QC; chuyển trạm khi có luân chuyển cán bộ (GET/PATCH /api/auth/profiles)."
        meta={[
          { label: "Tổng tài khoản", value: String(profiles.length) },
          { label: "Số trạm", value: String(stations.length) },
          { label: "Chưa gán trạm", value: String(unassignedCount) },
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
          {unassignedCount > 0 && (
            <Panel
              className="lg:col-span-2 xl:col-span-3"
              title="Chưa gán trạm"
              actions={<Badge tone="warn">{unassignedCount}</Badge>}
              dense
            >
              {grouped.get(UNASSIGNED)!.map((p) => (
                <div
                  key={p.user_id}
                  className="flex flex-wrap items-center gap-2 border-b border-border/60 px-3 py-2 last:border-b-0"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12.5px] font-medium text-foreground">
                      {p.full_name || p.email || p.user_id}
                      {p.user_id === currentProfile?.user_id ? (
                        <span className="ml-1.5 text-muted-foreground">(bạn)</span>
                      ) : null}
                    </div>
                  </div>
                  <select
                    value={p.role === "QC_SUPERVISOR" ? "QC_SUPERVISOR" : "QC_OPERATOR"}
                    onChange={(e) => void changeRole(p, e.target.value as Role)}
                    disabled={p.user_id === currentProfile?.user_id || movingId === p.user_id}
                    className={moveSelectClass}
                  >
                    <option value="QC_OPERATOR">QC_OPERATOR</option>
                    <option value="QC_SUPERVISOR">QC_SUPERVISOR</option>
                  </select>
                  <select
                    value=""
                    onChange={(e) => e.target.value && void move(p, e.target.value)}
                    disabled={movingId === p.user_id}
                    className={moveSelectClass}
                  >
                    <option value="">Gán vào trạm…</option>
                    {stations.map((s) => (
                      <option key={s.station_id} value={s.station_id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
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
                    <div
                      key={p.user_id}
                      className="flex flex-wrap items-center gap-2 border-b border-border/60 px-3 py-2 last:border-b-0"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[12.5px] font-medium text-foreground">
                          {p.full_name || p.email || p.user_id}
                          {p.user_id === currentProfile?.user_id ? (
                            <span className="ml-1.5 text-muted-foreground">(bạn)</span>
                          ) : null}
                        </div>
                        <Badge
                          tone={p.role === "QC_SUPERVISOR" ? "info" : "neutral"}
                          className="mt-1"
                        >
                          {p.role}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <select
                          value={p.role === "QC_SUPERVISOR" ? "QC_SUPERVISOR" : "QC_OPERATOR"}
                          onChange={(e) => void changeRole(p, e.target.value as Role)}
                          disabled={p.user_id === currentProfile?.user_id || movingId === p.user_id}
                          title={
                            p.user_id === currentProfile?.user_id
                              ? "Không thể tự thay đổi vai trò của chính mình"
                              : "Đổi vai trò"
                          }
                          className={moveSelectClass}
                        >
                          <option value="QC_OPERATOR">QC_OPERATOR</option>
                          <option value="QC_SUPERVISOR">QC_SUPERVISOR</option>
                        </select>
                        <select
                          value={s.station_id}
                          onChange={(e) =>
                            void move(p, e.target.value === UNASSIGNED ? "" : e.target.value)
                          }
                          disabled={movingId === p.user_id}
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
                      </div>
                    </div>
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
