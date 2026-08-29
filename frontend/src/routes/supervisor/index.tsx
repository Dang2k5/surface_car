import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AlertTriangle, CircleCheck, FileDown } from "lucide-react";
import { DonutChart, QualityStream } from "@/components/supervisor/charts";
import {
  Badge,
  Btn,
  Drawer,
  Field,
  KpiCard,
  PageHeader,
  Panel,
  SegmentedControl,
  Select,
  severityTone,
  TextField,
} from "@/components/supervisor/ui";
import {
  useAgentRuns,
  useAgentStatus,
  useDownloadTrendReport,
  useLots,
  useQualityAlerts,
  useShifts,
  useStations,
  useTrend,
} from "@/lib/queries";
import {
  dedupeByVehicle,
  defectMixFromRuns,
  severityMixFromRuns,
  trendToPoints,
} from "@/lib/supervisor-aggregate";
import { formatZoneName } from "@/lib/detection-geometry";
import type { QualityAlert } from "@/lib/api-types";

export const Route = createFileRoute("/supervisor/")({
  head: () => ({
    meta: [
      { title: "Trung tâm điều hành chất lượng — QC Supervisor" },
      {
        name: "description",
        content:
          "Tổng quan chất lượng theo thời gian thực cho QC Supervisor: KPI, xu hướng PASS/FAIL, phân bố lỗi và cảnh báo cần xử lý.",
      },
    ],
  }),
  component: ControlCenter,
});

type GroupBy = "hour" | "day" | "shift" | "lot";

function ControlCenter() {
  const [groupBy, setGroupBy] = useState<GroupBy>("hour");
  const [alert, setAlert] = useState<QualityAlert | null>(null);
  const [filterShift, setFilterShift] = useState("");
  const [filterLot, setFilterLot] = useState("");
  const [filterStation, setFilterStation] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const navigate = useNavigate();

  const runsQuery = useAgentRuns();
  const statusQuery = useAgentStatus();
  const alertsQuery = useQualityAlerts();
  const shiftsQuery = useShifts();
  const lotsQuery = useLots();
  const stationsQuery = useStations();
  const downloadReport = useDownloadTrendReport();
  const trendFilters = {
    ...(filterShift ? { shiftId: filterShift } : {}),
    ...(filterLot ? { lotId: filterLot } : {}),
    ...(filterStation ? { stationId: filterStation } : {}),
    ...(dateFrom ? { dateFrom } : {}),
    ...(dateTo ? { dateTo } : {}),
  };
  const trendQuery = useTrend(groupBy, trendFilters);

  const displayRuns = runsQuery.data ? dedupeByVehicle(runsQuery.data) : [];
  const inspected = displayRuns.length;
  const passCount = displayRuns.filter((r) => r.state.final_status === "PASS").length;
  const failCount = displayRuns.filter(
    (r) => r.status === "COMPLETED" && r.state.final_status && r.state.final_status !== "PASS",
  ).length;
  const hitlPending = displayRuns.filter((r) => r.status === "INTERRUPTED").length;
  const passRate = inspected ? Math.round((passCount / inspected) * 1000) / 10 : 0;
  const failRate = inspected ? Math.round((failCount / inspected) * 1000) / 10 : 0;
  const engineOnline = statusQuery.data?.langgraph === "READY";
  const alerts = alertsQuery.data?.alerts ?? [];
  const criticalCount = alerts.filter((a) => a.severity === "CRITICAL").length;
  const points = trendQuery.data ? trendToPoints(trendQuery.data) : [];
  const defectMix = runsQuery.data ? defectMixFromRuns(runsQuery.data) : [];
  const severityMix = runsQuery.data ? severityMixFromRuns(runsQuery.data) : [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Trung tâm điều hành chất lượng"
        right={
          <div className="flex items-center gap-2">
            <Badge tone={engineOnline ? "pass" : "fail"} dot>
              {engineOnline ? "Hệ thống hoạt động" : "Mất kết nối backend"}
            </Badge>
            {criticalCount > 0 ? (
              <Badge tone="fail">{criticalCount} cảnh báo nghiêm trọng</Badge>
            ) : null}
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-5">
        <KpiCard
          label="Xe đã kiểm"
          value={runsQuery.isPending ? "—" : String(inspected)}
          tone="info"
          sub="Số xe khác nhau đã ghi nhận"
        />
        <KpiCard
          label="PASS"
          value={runsQuery.isPending ? "—" : String(passCount)}
          tone="pass"
          sub={`${passRate}% tỷ lệ đạt`}
        />
        <KpiCard
          label="FAIL"
          value={runsQuery.isPending ? "—" : String(failCount)}
          tone="fail"
          sub={`${failRate}% tỷ lệ lỗi`}
        />
        <KpiCard
          label="Chờ HITL"
          value={runsQuery.isPending ? "—" : String(hitlPending)}
          tone="warn"
          sub="Đang chờ nhân viên xác nhận"
          to="/supervisor/escalations"
        />
        <KpiCard
          label="Bất thường"
          value={alertsQuery.isPending ? "—" : String(alerts.length)}
          tone={alerts.length > 0 ? "warn" : "neutral"}
          sub={`${criticalCount} nghiêm trọng`}
          to="/supervisor/anomalies"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <Panel
          title="Xu hướng chất lượng"
          actions={
            <SegmentedControl<GroupBy>
              value={groupBy}
              onChange={setGroupBy}
              options={[
                { key: "hour", label: "Giờ" },
                { key: "day", label: "Ngày" },
                { key: "shift", label: "Ca" },
                { key: "lot", label: "Lô" },
              ]}
            />
          }
        >
          <div className="mb-3 flex flex-wrap items-end gap-2 border-b border-border pb-3">
            <TextField label="Từ ngày" type="date" value={dateFrom} onChange={setDateFrom} />
            <TextField label="Đến ngày" type="date" value={dateTo} onChange={setDateTo} />
            <Select
              label="Ca làm việc"
              value={filterShift}
              onChange={setFilterShift}
              options={[
                { value: "", label: "Tất cả" },
                ...(shiftsQuery.data ?? []).map((s) => ({ value: s.shift_id, label: s.name })),
              ]}
            />
            <Select
              label="Lô sản xuất"
              value={filterLot}
              onChange={setFilterLot}
              options={[
                { value: "", label: "Tất cả" },
                ...(lotsQuery.data ?? []).map((l) => ({ value: l.lot_id, label: l.lot_id })),
              ]}
            />
            <Select
              label="Trạm"
              value={filterStation}
              onChange={setFilterStation}
              options={[
                { value: "", label: "Tất cả" },
                ...(stationsQuery.data ?? []).map((s) => ({ value: s.station_id, label: s.name })),
              ]}
            />
            <Btn
              variant="outline"
              className="ml-auto"
              onClick={() => downloadReport.mutate({ groupBy, filters: trendFilters })}
              disabled={downloadReport.isPending}
            >
              <FileDown className="size-3.5" />
              {downloadReport.isPending ? "Đang xuất…" : "Xuất báo cáo"}
            </Btn>
          </div>
          {trendQuery.isPending ? (
            <div className="flex h-[300px] items-center justify-center text-sm text-muted-foreground">
              Đang tải dữ liệu…
            </div>
          ) : points.length === 0 ? (
            <div className="flex h-[300px] items-center justify-center text-sm text-muted-foreground">
              Chưa có dữ liệu trend.
            </div>
          ) : (
            <QualityStream
              data={points}
              onPointClick={() => navigate({ to: "/supervisor/inspections" })}
            />
          )}
        </Panel>

        <Panel
          title="Cảnh báo cần chú ý"
          subtitle={`${alerts.length} cảnh báo đang hoạt động`}
          dense
          bodyClassName="divide-y divide-border"
        >
          {alerts.length === 0 ? (
            <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
              <CircleCheck className="size-6 text-success" />
              <p className="text-sm text-muted-foreground">
                Không có cảnh báo — mọi hệ thống bình thường.
              </p>
            </div>
          ) : (
            alerts.map((a) => (
              <button
                key={a.id}
                onClick={() => setAlert(a)}
                className="block w-full px-4 py-3 text-left transition-colors hover:bg-surface-2"
              >
                <div className="flex items-center gap-2">
                  <Badge tone={severityTone(a.severity)} dot>
                    {a.severity}
                  </Badge>
                  <span className="truncate text-[12.5px] font-medium">
                    {a.defect_type} · {formatZoneName(a.zone_name)}
                  </span>
                  <span className="num ml-auto text-[11px] text-muted-foreground">
                    {a.last_seen}
                  </span>
                </div>
                <p className="mt-1.5 line-clamp-2 text-[12px] leading-snug text-muted-foreground">
                  {a.message_vi || a.message_en}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="num text-[11px] text-muted-foreground">
                    {a.camera_id} · {a.occurrence_count} lần
                  </span>
                  <span className="num text-[11px] text-warning">
                    {a.affected_vehicle_count} xe bị ảnh hưởng
                  </span>
                </div>
              </button>
            ))
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel title="Phân bố loại lỗi">
          {defectMix.length === 0 ? (
            <div className="flex h-[210px] items-center justify-center text-sm text-muted-foreground">
              Chưa có phát hiện lỗi nào.
            </div>
          ) : (
            <DonutChart data={defectMix} />
          )}
        </Panel>
        <Panel title="Phân bố mức độ nghiêm trọng">
          {severityMix.length === 0 ? (
            <div className="flex h-[210px] items-center justify-center text-sm text-muted-foreground">
              Chưa có phát hiện lỗi nào.
            </div>
          ) : (
            <DonutChart data={severityMix} />
          )}
        </Panel>
      </div>

      <Drawer
        open={!!alert}
        onClose={() => setAlert(null)}
        title={alert ? `${alert.defect_type} · ${formatZoneName(alert.zone_name)}` : ""}
        subtitle={alert ? `${alert.camera_id} · phát hiện lần đầu ${alert.first_seen}` : ""}
        width="max-w-[680px]"
      >
        {alert && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Badge tone={severityTone(alert.severity)}>{alert.severity}</Badge>
              <Badge tone="info">{alert.status}</Badge>
            </div>
            <p className="text-[13px] leading-relaxed text-foreground">
              {alert.message_vi || alert.message_en}
            </p>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Field label="Camera" mono>
                {alert.camera_id}
              </Field>
              <Field label="Số lần xuất hiện" mono>
                {alert.occurrence_count}
              </Field>
              <Field label="Xe bị ảnh hưởng" mono>
                {alert.affected_vehicle_count}
              </Field>
              <Field label="Độ tin cậy TB" mono>
                {alert.average_confidence.toFixed(1)}%
              </Field>
            </div>
            <Panel title="Nguyên nhân dự đoán">
              <p className="text-[12.5px] text-foreground">
                {alert.predicted_root_cause || "Chưa xác định"}
              </p>
            </Panel>
            <Panel title="Khuyến nghị xử lý">
              <p className="text-[12.5px] text-foreground">
                {alert.actionable_routing_command || "—"}
              </p>
              {alert.upstream_target_shop ? (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Chuyển tới: {alert.upstream_target_shop}
                </p>
              ) : null}
            </Panel>
            <div className="flex flex-wrap gap-1.5">
              <AlertTriangle className="size-3.5 text-muted-foreground" />
              {alert.affected_vehicle_ids.slice(0, 12).map((v) => (
                <Badge key={v} tone="neutral">
                  {v}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
