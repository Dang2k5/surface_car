import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  Badge,
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
import { assetUrl } from "@/lib/auth";
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

function InspectionExplorer() {
  const runsQuery = useAgentRuns();
  const [search, setSearch] = useState("");
  const [result, setResult] = useState<ResultFilter>("all");
  const [selected, setSelected] = useState<GraphRun | null>(null);

  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return runs.filter((r) => {
      if (result !== "all" && resultOf(r) !== result) return false;
      if (!q) return true;
      return (
        r.state.vehicle_id.toLowerCase().includes(q) ||
        r.state.inspection_id.toLowerCase().includes(q) ||
        (r.state.station_id ?? "").toLowerCase().includes(q)
      );
    });
  }, [runs, search, result]);

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
                <Th>Xe</Th>
                <Th>Trạm</Th>
                <Th>Zone</Th>
                <Th>Loại lỗi</Th>
                <Th>Kết quả</Th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => {
                const res = resultOf(r);
                return (
                  <Tr key={r.thread_id} onClick={() => setSelected(r)}>
                    <Td className="num">{r.state.inspection_id}</Td>
                    <Td className="font-medium">{r.state.vehicle_id}</Td>
                    <Td>{r.state.station_id || "—"}</Td>
                    <Td>{r.state.zone_name}</Td>
                    <Td>{r.state.defect_type || "—"}</Td>
                    <Td>
                      <Badge tone={res === "pass" ? "pass" : res === "fail" ? "fail" : "warn"}>
                        {res === "pass" ? "PASS" : res === "fail" ? "FAIL" : "CHỜ DUYỆT"}
                      </Badge>
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Panel>

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected ? `${selected.state.vehicle_id} · #${selected.state.inspection_id}` : ""}
        subtitle={selected ? `${selected.state.vehicle_model} · ${selected.state.zone_name}` : ""}
        width="max-w-[760px]"
      >
        {selected && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
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
            </div>

            {selected.state.overlay_image_url || selected.state.crop_image_url ? (
              <Panel title="Ảnh bằng chứng">
                <img
                  src={assetUrl(selected.state.overlay_image_url || selected.state.crop_image_url)}
                  alt="Bằng chứng lỗi"
                  className="max-h-[360px] w-full rounded-sm border border-border object-contain"
                />
              </Panel>
            ) : null}

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
                      className="flex items-center justify-between gap-3 rounded-sm border border-border bg-surface-2 px-3 py-2"
                    >
                      <span className="min-w-0 truncate font-mono text-xs text-foreground">
                        {step.node}
                      </span>
                      <span className="shrink-0 font-mono text-[10px] tracking-wider text-muted-foreground">
                        {step.status}
                      </span>
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
