import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { AlertTriangle, CircleCheck } from "lucide-react";
import {
  Badge,
  Drawer,
  EmptyState,
  Field,
  PageHeader,
  Panel,
  Timeline,
} from "@/components/supervisor/ui";
import { useQualityAlerts } from "@/lib/queries";
import type { QualityAlert } from "@/lib/api-types";

export const Route = createFileRoute("/supervisor/anomalies")({
  head: () => ({
    meta: [{ title: "Bất thường hệ thống — QC Supervisor" }],
  }),
  component: Anomalies,
});

function Anomalies() {
  const alertsQuery = useQualityAlerts();
  const [selected, setSelected] = useState<QualityAlert | null>(null);
  const alerts = alertsQuery.data?.alerts ?? [];
  const criticalCount = alerts.filter((a) => a.severity === "CRITICAL").length;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Bất thường hệ thống"
        description="Cảnh báo lặp lại được phát hiện tự động từ cửa sổ trượt các inspection gần đây (GET /api/quality-alerts)."
        meta={[
          { label: "Tổng số", value: String(alerts.length) },
          { label: "Nghiêm trọng", value: String(criticalCount) },
          { label: "Cửa sổ", value: alertsQuery.data ? `${alertsQuery.data.window_hours}h` : "—" },
        ]}
      />

      {alertsQuery.isPending ? (
        <Panel>
          <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
            Đang tải…
          </div>
        </Panel>
      ) : alerts.length === 0 ? (
        <Panel>
          <EmptyState
            title="Không có bất thường nào"
            description="Không có cảnh báo lặp lại nào được phát hiện trong cửa sổ theo dõi hiện tại."
          />
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {alerts.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelected(a)}
              className="panel flex flex-col gap-2 p-4 text-left transition-colors hover:border-border-strong"
            >
              <div className="flex items-center gap-2">
                <Badge tone={a.severity === "CRITICAL" ? "fail" : "warn"} dot>
                  {a.severity}
                </Badge>
                <span className="truncate text-[13px] font-semibold">
                  {a.defect_type} · {a.zone_name}
                </span>
              </div>
              <p className="line-clamp-2 text-[12.5px] leading-snug text-muted-foreground">
                {a.message_vi || a.message_en}
              </p>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                <span className="num">{a.camera_id}</span>
                <span className="num text-warning">{a.occurrence_count} lần lặp lại</span>
                <span className="num">{a.affected_vehicle_count} xe</span>
                <span className="num ml-auto">{a.last_seen}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected ? `${selected.defect_type} · ${selected.zone_name}` : ""}
        subtitle={selected ? `Trigger: ${selected.trigger_type}` : ""}
        width="max-w-[680px]"
      >
        {selected && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Badge tone={selected.severity === "CRITICAL" ? "fail" : "warn"}>
                {selected.severity}
              </Badge>
              <Badge tone="info">{selected.status}</Badge>
            </div>
            <p className="text-[13px] leading-relaxed text-foreground">
              {selected.message_vi || selected.message_en}
            </p>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Field label="Camera" mono>
                {selected.camera_id}
              </Field>
              <Field label="Số lần xuất hiện" mono>
                {selected.occurrence_count}
              </Field>
              <Field label="Liên tiếp" mono>
                {selected.consecutive_count}
              </Field>
              <Field label="Cửa sổ kiểm tra" mono>
                {selected.window_size} inspection
              </Field>
              <Field label="Xe bị ảnh hưởng" mono>
                {selected.affected_vehicle_count}
              </Field>
              <Field label="Độ tin cậy TB" mono>
                {selected.average_confidence.toFixed(1)}%
              </Field>
              <Field label="Độ tin cậy tối đa" mono>
                {selected.maximum_confidence.toFixed(1)}%
              </Field>
              <Field label="Mã lỗi liên quan" mono>
                {selected.related_defect_codes.join(", ") || "—"}
              </Field>
            </div>

            <Panel title="Nguyên nhân dự đoán">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
                <p className="text-[12.5px] text-foreground">
                  {selected.predicted_root_cause || "Chưa xác định"}
                </p>
              </div>
            </Panel>

            <Panel title="Khuyến nghị xử lý">
              <p className="text-[12.5px] text-foreground">
                {selected.actionable_routing_command || "—"}
              </p>
              {selected.upstream_target_shop ? (
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  Chuyển tới bộ phận: {selected.upstream_target_shop}
                </p>
              ) : null}
            </Panel>

            <Panel title="Mốc thời gian">
              <Timeline
                items={[
                  {
                    t: selected.first_seen,
                    text: `Phát hiện lần đầu · ${selected.defect_type}`,
                    kind: "defect",
                  },
                  { t: selected.last_seen, text: "Lần xuất hiện gần nhất", kind: "defect" },
                ]}
              />
            </Panel>

            <div>
              <div className="label-caps mb-1.5">Các xe bị ảnh hưởng</div>
              <div className="flex flex-wrap gap-1.5">
                {selected.affected_vehicle_ids.length === 0 ? (
                  <span className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                    <CircleCheck className="size-3.5" /> Không có
                  </span>
                ) : (
                  selected.affected_vehicle_ids.map((v) => (
                    <Badge key={v} tone="neutral">
                      {v}
                    </Badge>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
