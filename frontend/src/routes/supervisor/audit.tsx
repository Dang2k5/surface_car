import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  Badge,
  Drawer,
  EmptyState,
  Field,
  KpiCard,
  PageHeader,
  Panel,
  Table,
  Td,
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

function Audit() {
  const decisionsQuery = useQcDecisions();
  const [selected, setSelected] = useState<QcDecision | null>(null);
  const decisions = useMemo(() => decisionsQuery.data ?? [], [decisionsQuery.data]);

  const counts = useMemo(() => {
    const c = { approve: 0, reject: 0, override: 0 };
    for (const d of decisions) {
      if (d.action === "APPROVE") c.approve++;
      else if (d.action === "REJECT") c.reject++;
      else if (d.action === "OVERRIDE") c.override++;
    }
    return c;
  }, [decisions]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Nhật ký & Override"
        meta={[{ label: "Tổng số", value: String(decisions.length) }]}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
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
      </div>

      <Panel dense>
        {decisionsQuery.isPending ? (
          <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
            Đang tải…
          </div>
        ) : decisions.length === 0 ? (
          <EmptyState
            title="Chưa có quyết định nào"
            description="Chưa có bản ghi QC decision nào được tạo."
          />
        ) : (
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
              {decisions.map((d) => (
                <Tr key={d.decision_id} onClick={() => setSelected(d)}>
                  <Td className="num">{d.created_at}</Td>
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
        )}
      </Panel>

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected ? `${selected.action} · ${selected.inspection_id}` : ""}
        subtitle={selected ? `${selected.created_at} · ${selected.reviewer}` : ""}
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
