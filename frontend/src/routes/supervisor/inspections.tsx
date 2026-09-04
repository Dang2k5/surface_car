import { createFileRoute } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";
import {
  Badge,
  Btn,
  Drawer,
  EmptyState,
  Field,
  PageHeader,
  Panel,
  Select,
  Table,
  Td,
  TextField,
  Th,
  Tr,
} from "@/components/supervisor/ui";
import { camerasFromState, defectsFromState, formatAffectedZones } from "@/lib/detection-geometry";
import { useAgentRuns } from "@/lib/queries";
import type { GraphRun } from "@/lib/api-types";

export const Route = createFileRoute("/supervisor/inspections")({
  head: () => ({
    meta: [{ title: "Tra cứu inspection — QC Supervisor" }],
  }),
  component: InspectionExplorer,
});

type ResultFilter = "all" | "pass" | "fail" | "pending";

function resultOf(r: GraphRun): ResultFilter {
  if (r.status === "INTERRUPTED") return "pending";
  if (r.state.final_status === "PASS") return "pass";
  if (r.state.final_status) return "fail";
  return "pending";
}

const NO_LOT = "Không có lô";

function lotOf(r: GraphRun): string {
  return r.state.lot_id || NO_LOT;
}

// submitted_by (set for every run since the HITL/line-control rollout) is who actually ran
// the inspection. Older runs predating that field fall back to the HITL reviewer, which is
// the closest available signal but only exists once a case has been resolved.
function performerOf(r: GraphRun): string {
  return (
    r.state.submitted_by ||
    r.state.human_decision?.reviewer ||
    r.state.qc_decision_record?.reviewer ||
    "—"
  );
}

function timeOf(r: GraphRun): string {
  return r.state._persisted_at ?? r.state.qc_decision_record?.created_at ?? "";
}

function formatDateTime(time: string): string {
  if (!time) return "—";
  const d = new Date(time);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function InspectionExplorer() {
  const runsQuery = useAgentRuns();
  const [search, setSearch] = useState("");
  const [result, setResult] = useState<ResultFilter>("all");
  const [lotFilter, setLotFilter] = useState("all");
  const [selected, setSelected] = useState<GraphRun | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);

  const lotOptions = useMemo(() => {
    const ids = new Set(runs.map((r) => r.state.lot_id).filter((id): id is string => !!id));
    return Array.from(ids).sort((a, b) => a.localeCompare(b));
  }, [runs]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const matches = runs.filter((r) => {
      if (result !== "all" && resultOf(r) !== result) return false;
      if (lotFilter !== "all" && lotOf(r) !== lotFilter) return false;
      if (!q) return true;
      return (
        r.state.vehicle_id.toLowerCase().includes(q) ||
        r.state.inspection_id.toLowerCase().includes(q) ||
        (r.state.station_id ?? "").toLowerCase().includes(q)
      );
    });
    // Group by lot: stable-sort by lot id so every inspection from the same lot renders
    // together, preserving each lot's own recency order (runs arrive newest-first).
    // No-lot inspections sort last rather than first.
    return [...matches].sort((a, b) => {
      const la = lotOf(a);
      const lb = lotOf(b);
      if (la === lb) return 0;
      if (la === NO_LOT) return 1;
      if (lb === NO_LOT) return -1;
      return la.localeCompare(lb);
    });
  }, [runs, search, result, lotFilter]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const paged = useMemo(
    () => filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize),
    [filtered, currentPage],
  );

  useEffect(() => {
    setPage(1);
  }, [search, result, lotFilter]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Tra cứu inspection"
        meta={[
          { label: "Tổng số", value: String(runs.length) },
          { label: "Hiển thị", value: String(filtered.length) },
        ]}
        right={
          <div className="flex items-end gap-2">
            <TextField
              label="Tìm kiếm"
              value={search}
              onChange={setSearch}
              placeholder="Xe, inspection, trạm…"
            />
            <Select
              label="Kết quả"
              value={result}
              onChange={(v) => setResult(v as ResultFilter)}
              options={[
                { value: "all", label: "Tất cả" },
                { value: "pass", label: "PASS" },
                { value: "fail", label: "FAIL" },
                { value: "pending", label: "Đang chờ" },
              ]}
            />
            <Select
              label="Lô"
              value={lotFilter}
              onChange={setLotFilter}
              options={[
                { value: "all", label: "Tất cả lô" },
                ...lotOptions.map((id) => ({ value: id, label: id })),
              ]}
            />
          </div>
        }
      />

      <Panel dense>
        {runsQuery.isPending ? (
          <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
            Đang tải…
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            title="Không tìm thấy inspection"
            description="Thử điều chỉnh bộ lọc hoặc từ khóa tìm kiếm."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Inspection</Th>
                <Th>Thời gian</Th>
                <Th>Xe</Th>
                <Th>Trạm</Th>
                <Th>Vùng lỗi</Th>
                <Th>Loại lỗi</Th>
                <Th>Kết quả</Th>
                <Th>Người thực hiện</Th>
              </tr>
            </thead>
            <tbody>
              {paged.map((r, i) => {
                const res = resultOf(r);
                const lotId = lotOf(r);
                const showLotHeader = i === 0 || lotOf(paged[i - 1]!) !== lotId;
                return (
                  <Fragment key={r.thread_id}>
                    {showLotHeader ? (
                      <tr className="bg-surface-2">
                        <td
                          colSpan={7}
                          className="px-3 py-1.5 font-mono text-[11px] font-semibold tracking-wider text-muted-foreground"
                        >
                          LÔ: {lotId}
                        </td>
                      </tr>
                    ) : null}
                    <Tr onClick={() => setSelected(r)}>
                      <Td className="num">{r.state.inspection_id}</Td>
                      <Td className="font-mono text-xs">{formatDateTime(timeOf(r))}</Td>
                      <Td className="font-medium">{r.state.vehicle_id}</Td>
                      <Td>{r.state.station_id || "—"}</Td>
                      <Td className="font-mono text-xs">
                        {formatAffectedZones(r.state.affected_zones)}
                      </Td>
                      <Td>{r.state.defect_type || "—"}</Td>
                      <Td>
                        <Badge tone={res === "pass" ? "pass" : res === "fail" ? "fail" : "warn"}>
                          {res === "pass" ? "PASS" : res === "fail" ? "FAIL" : "CHỜ DUYỆT"}
                        </Badge>
                      </Td>
                      <Td>{performerOf(r)}</Td>
                    </Tr>
                  </Fragment>
                );
              })}
            </tbody>
          </Table>
        )}
        {filtered.length > 0 ? (
          <div className="flex items-center justify-between border-t border-border px-3 py-2">
            <span className="text-xs text-muted-foreground">
              Trang {currentPage}/{pageCount} · {filtered.length} bản ghi
            </span>
            <div className="flex items-center gap-1">
              <Btn
                variant="outline"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
              >
                <ChevronLeft className="size-3.5" /> Trước
              </Btn>
              <Btn
                variant="outline"
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                disabled={currentPage === pageCount}
              >
                Sau <ChevronRight className="size-3.5" />
              </Btn>
            </div>
          </div>
        ) : null}
      </Panel>

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected ? `${selected.state.vehicle_id} · #${selected.state.inspection_id}` : ""}
        subtitle={
          selected
            ? `${selected.state.vehicle_model} · ${formatAffectedZones(selected.state.affected_zones)}`
            : ""
        }
        width="max-w-[760px]"
      >
        {selected && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Field label="Thời gian" mono>
                {formatDateTime(timeOf(selected))}
              </Field>
              <Field label="Trạm" mono>
                {selected.state.station_id || "—"}
              </Field>
              <Field label="Lô" mono>
                {selected.state.lot_id || "—"}
              </Field>
              <Field label="Ca" mono>
                {selected.state.shift_id || "—"}
              </Field>
              <Field label="Ngày SX" mono>
                {selected.state.production_date || "—"}
              </Field>
              <Field label="Loại lỗi">{selected.state.defect_type || "—"}</Field>
              <Field label="Mức độ">{selected.state.severity || "—"}</Field>
              <Field label="Độ tin cậy" mono>
                {selected.state.confidence != null
                  ? `${Math.round(selected.state.confidence * 100)}%`
                  : "—"}
              </Field>
              <Field label="Trạng thái cuối">{selected.state.final_status || "—"}</Field>
              <Field label="Người thực hiện">{performerOf(selected)}</Field>
            </div>

            {(() => {
              const cameras = camerasFromState(selected.state).filter((c) => c.image);
              const defects = defectsFromState(selected.state);
              if (cameras.length === 0) return null;
              return (
                <Panel title={`Ảnh bằng chứng theo camera (${cameras.length})`}>
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                    {cameras.map((cam) => {
                      const camDefects = defects.filter((d) => d.camera === cam.id);
                      return (
                        <div key={cam.id} className="space-y-1.5">
                          <img
                            src={cam.image}
                            alt={`${cam.id} ${cam.position}`}
                            className="aspect-[4/3] w-full rounded-sm border border-border object-cover"
                          />
                          <div className="flex items-center justify-between font-mono text-[10px] text-muted-foreground">
                            <span>
                              {cam.id} · {cam.position}
                            </span>
                            <Badge tone={cam.health === "DEGRADED" ? "fail" : "pass"}>
                              {camDefects.length > 0 ? `${camDefects.length} lỗi` : "OK"}
                            </Badge>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Panel>
              );
            })()}

            {(() => {
              const defects = defectsFromState(selected.state);
              if (defects.length === 0) return null;
              return (
                <Panel title={`Chi tiết lỗi theo camera (${defects.length})`}>
                  <div className="space-y-2">
                    {defects.map((d) => (
                      <div
                        key={d.id}
                        className="grid grid-cols-[96px_1fr] gap-3 rounded-sm border border-border bg-surface-2 p-2"
                      >
                        {d.overlayImageUrl || d.cropImageUrl ? (
                          <img
                            src={d.overlayImageUrl || d.cropImageUrl}
                            alt={`${d.type} tại ${d.camera}`}
                            className="h-[72px] w-full rounded-sm border border-border object-cover"
                          />
                        ) : (
                          <div className="flex h-[72px] items-center justify-center rounded-sm border border-dashed border-border text-[10px] text-muted-foreground">
                            Không có ảnh
                          </div>
                        )}
                        <div className="min-w-0 space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-xs font-semibold text-foreground">
                              {d.camera} · {d.type}
                            </span>
                            <Badge
                              tone={
                                d.decision === "PASS" ? "pass" : d.decision === "FAIL" ? "fail" : "warn"
                              }
                            >
                              {d.decision}
                            </Badge>
                          </div>
                          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 font-mono text-[11px] text-muted-foreground">
                            <span>Vị trí: {d.location}</span>
                            <span>Độ tin cậy: {d.confidence}%</span>
                            <span>Kích thước: {d.measurement}</span>
                            <span>Ngưỡng: {d.threshold}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </Panel>
              );
            })()}

            {selected.state.human_decision ? (
              <Panel title="Quyết định con người">
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Hành động">{selected.state.human_decision.action}</Field>
                  <Field label="Người duyệt">{selected.state.human_decision.reviewer}</Field>
                  <Field label="Lý do">{selected.state.human_decision.reason}</Field>
                </div>
              </Panel>
            ) : null}

            {selected.state.execution_trace?.length ? (
              <Panel title="Nhật ký thực thi">
                <ol className="space-y-1.5">
                  {selected.state.execution_trace.map((step, i) => (
                    <li
                      key={`${step.node}-${i}`}
                      className="space-y-1 rounded-sm border border-border bg-surface-2 px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="min-w-0 truncate font-mono text-xs font-semibold text-foreground">
                          {step.node}
                        </span>
                        <span className="shrink-0 font-mono text-[10px] tracking-wider text-muted-foreground">
                          {step.status}
                        </span>
                      </div>
                      {step.detail ? (
                        <p className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-muted-foreground">
                          {step.detail}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </Panel>
            ) : null}
          </div>
        )}
      </Drawer>
    </div>
  );
}
