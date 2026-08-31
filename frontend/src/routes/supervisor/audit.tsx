import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Download } from "lucide-react";
import {
  Badge,
  Btn,
  Drawer,
  EmptyState,
  Field,
  KpiCard,
  PageHeader,
  Panel,
  Select,
  Table,
  Td,
  TextField,
  Th,
  Tr,
} from "@/components/supervisor/ui";
import { useQcDecisions } from "@/lib/queries";
import type { QcDecision } from "@/lib/api-types";

export const Route = createFileRoute("/supervisor/audit")({
  head: () => ({
    meta: [{ title: "Nhật ký & Override — QC Supervisor" }],
  }),
  component: Audit,
});

const PAGE_SIZE = 20;

// Same format as "Tra cứu inspection" (supervisor/inspections.tsx's formatDateTime), kept in
// sync manually so a decision's timestamp reads identically whether it's viewed from this log
// or cross-referenced on that page.
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

function downloadCsv(rows: QcDecision[]) {
  const header = [
    "created_at",
    "reviewer",
    "action",
    "inspection_id",
    "vehicle_id",
    "defect_type",
    "severity",
    "disposition",
    "reason",
  ];
  const escape = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const body = rows.map((d) =>
    [
      d.created_at,
      d.reviewer,
      d.action,
      d.inspection_id,
      d.vehicle_id,
      d.defect_type,
      d.severity,
      d.disposition,
      d.reason,
    ]
      .map((v) => escape(String(v ?? "")))
      .join(","),
  );
  const blob = new Blob([[header.join(","), ...body].join("\n")], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `nhat-ky-override-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function Audit() {
  const decisionsQuery = useQcDecisions();
  const [selected, setSelected] = useState<QcDecision | null>(null);
  const decisions = useMemo(() => decisionsQuery.data ?? [], [decisionsQuery.data]);

  const [action, setAction] = useState("all");
  const [severity, setSeverity] = useState("all");
  const [reviewer, setReviewer] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(0);

  const severities = useMemo(
    () => Array.from(new Set(decisions.map((d) => d.severity).filter(Boolean))),
    [decisions],
  );

  const filtered = useMemo(() => {
    return decisions.filter((d) => {
      if (action !== "all" && d.action !== action) return false;
      if (severity !== "all" && d.severity !== severity) return false;
      if (reviewer && !d.reviewer.toLowerCase().includes(reviewer.toLowerCase())) return false;
      if (vehicle && !d.vehicle_id.toLowerCase().includes(vehicle.toLowerCase())) return false;
      const day = d.created_at.slice(0, 10);
      if (from && day < from) return false;
      if (to && day > to) return false;
      return true;
    });
  }, [decisions, action, severity, reviewer, vehicle, from, to]);

  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  function resetFilters() {
    setAction("all");
    setSeverity("all");
    setReviewer("");
    setVehicle("");
    setFrom("");
    setTo("");
    setPage(0);
  }

  const counts = useMemo(() => {
    const c = { approve: 0, reject: 0, override: 0 };
    for (const d of filtered) {
      if (d.action === "APPROVE") c.approve++;
      else if (d.action === "REJECT") c.reject++;
      else if (d.action === "OVERRIDE") c.override++;
    }
    return c;
  }, [filtered]);

  const agreementRate =
    filtered.length > 0 ? Math.round(((filtered.length - counts.override) / filtered.length) * 100) : 0;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Nhật ký & Override"
        meta={[
          { label: "Tổng số", value: String(decisions.length) },
          { label: "Đang lọc", value: String(filtered.length) },
        ]}
        right={
          <Btn variant="outline" onClick={() => downloadCsv(filtered)} disabled={filtered.length === 0}>
            <Download className="size-3.5" /> XUẤT CSV
          </Btn>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Xác nhận AI"
          value={String(counts.approve)}
          tone="pass"
          sub="Action = APPROVE"
        />
        <KpiCard
          label="Từ chối AI"
          value={String(counts.reject)}
          tone="fail"
          sub="Action = REJECT"
        />
        <KpiCard
          label="Override"
          value={String(counts.override)}
          tone="warn"
          sub="Action = OVERRIDE"
        />
        <KpiCard
          label="Tỷ lệ đồng thuận AI"
          value={`${agreementRate}%`}
          tone={agreementRate >= 90 ? "pass" : agreementRate >= 75 ? "warn" : "fail"}
          sub="Không bị Override / Tổng số"
        />
      </div>

      <Panel dense title="Bộ lọc">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <Select
            label="Hành động"
            value={action}
            onChange={(v) => {
              setAction(v);
              setPage(0);
            }}
            options={[
              { value: "all", label: "Tất cả" },
              { value: "APPROVE", label: "APPROVE" },
              { value: "REJECT", label: "REJECT" },
              { value: "OVERRIDE", label: "OVERRIDE" },
            ]}
          />
          <Select
            label="Mức độ"
            value={severity}
            onChange={(v) => {
              setSeverity(v);
              setPage(0);
            }}
            options={[
              { value: "all", label: "Tất cả" },
              ...severities.map((s) => ({ value: s, label: s })),
            ]}
          />
          <TextField
            label="Người duyệt"
            value={reviewer}
            onChange={(v) => {
              setReviewer(v);
              setPage(0);
            }}
            placeholder="Tìm theo tên..."
          />
          <TextField
            label="Xe"
            value={vehicle}
            onChange={(v) => {
              setVehicle(v);
              setPage(0);
            }}
            placeholder="Mã xe..."
          />
          <TextField
            label="Từ ngày"
            type="date"
            value={from}
            onChange={(v) => {
              setFrom(v);
              setPage(0);
            }}
          />
          <TextField
            label="Đến ngày"
            type="date"
            value={to}
            onChange={(v) => {
              setTo(v);
              setPage(0);
            }}
          />
        </div>
        <div className="mt-2 flex justify-end">
          <Btn onClick={resetFilters}>Xóa bộ lọc</Btn>
        </div>
      </Panel>

      <Panel dense>
        {decisionsQuery.isPending ? (
          <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
            Đang tải…
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            title="Không có bản ghi phù hợp"
            description="Không tìm thấy quyết định nào khớp với bộ lọc hiện tại."
          />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Thời gian</Th>
                  <Th>Người duyệt</Th>
                  <Th>Hành động</Th>
                  <Th>Đối tượng</Th>
                  <Th>Kết luận</Th>
                  <Th>Mức độ</Th>
                </tr>
              </thead>
              <tbody>
                {paged.map((d) => (
                  <Tr key={d.decision_id} onClick={() => setSelected(d)}>
                    <Td className="num font-mono text-xs">{formatDateTime(d.created_at)}</Td>
                    <Td className="font-medium">{d.reviewer}</Td>
                    <Td>
                      <Badge
                        tone={
                          d.action === "APPROVE" ? "pass" : d.action === "REJECT" ? "fail" : "warn"
                        }
                      >
                        {d.action}
                      </Badge>
                    </Td>
                    <Td className="num">{d.inspection_id}</Td>
                    <Td>{d.disposition}</Td>
                    <Td>{d.severity}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
            <div className="mt-3 flex items-center justify-between">
              <span className="text-[12px] text-muted-foreground">
                Trang {page + 1}/{pageCount} · {filtered.length} bản ghi
              </span>
              <div className="flex gap-2">
                <Btn variant="outline" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                  Trước
                </Btn>
                <Btn
                  variant="outline"
                  disabled={page >= pageCount - 1}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Sau
                </Btn>
              </div>
            </div>
          </>
        )}
      </Panel>

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected ? `${selected.action} · ${selected.inspection_id}` : ""}
        subtitle={selected ? `${formatDateTime(selected.created_at)} · ${selected.reviewer}` : ""}
        width="max-w-[640px]"
      >
        {selected && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
              <Field label="Xe" mono>
                {selected.vehicle_id}
              </Field>
              <Field label="Mã lỗi" mono>
                {selected.defect_code}
              </Field>
              <Field label="Loại lỗi">{selected.defect_type}</Field>
              <Field label="Vị trí">{selected.location || "—"}</Field>
              <Field label="Kích thước" mono>
                {selected.length_mm != null ? `${selected.length_mm} mm` : "—"}
              </Field>
              <Field label="Mức độ">{selected.severity}</Field>
              <Field label="Kết luận">{selected.disposition}</Field>
              <Field label="Thread" mono>
                {selected.thread_id || "—"}
              </Field>
            </div>
            <Panel title="Lý do">
              <p className="text-[12.5px] text-foreground">{selected.reason}</p>
            </Panel>
            {selected.notes ? (
              <Panel title="Ghi chú">
                <p className="text-[12.5px] text-foreground">{selected.notes}</p>
              </Panel>
            ) : null}
          </div>
        )}
      </Drawer>
    </div>
  );
}
