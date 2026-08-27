import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
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
  TextArea,
  TextField,
  Td,
  Th,
  Tr,
} from "@/components/supervisor/ui";
import { profileDisplayName, useAuth } from "@/lib/auth";
import { useAgentRuns, useResumeInspection } from "@/lib/queries";
import type { GraphRun } from "@/lib/api-types";

export const Route = createFileRoute("/supervisor/escalations")({
  head: () => ({
    meta: [{ title: "Hàng đợi leo thang — QC Supervisor" }],
  }),
  component: Escalations,
});

/** A case has passed the operator's own review (human_decision set) and is still
 * INTERRUPTED only when it's paused a second time at supervisor_review — i.e. the
 * operator chose "CHUYỂN CẤP XÉT DUYỆT" (OVERRIDE) and it now needs a supervisor's
 * APPROVE/REJECT (agent/graph/nodes.py's supervisor_review, backend/app/langgraph_api.py). */
function isPendingSupervisor(run: GraphRun): boolean {
  return run.status === "INTERRUPTED" && !!run.state.human_decision;
}

function Escalations() {
  const runsQuery = useAgentRuns();
  const { profile } = useAuth();
  const resume = useResumeInspection();

  const [station, setStation] = useState("all");
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [reason, setReason] = useState("");
  const [validationError, setValidationError] = useState("");

  useEffect(() => {
    if (profile) setReviewer((current) => current || profileDisplayName(profile));
  }, [profile]);

  const pending = (runsQuery.data ?? []).filter(isPendingSupervisor);
  const stations = Array.from(
    new Set(pending.map((r) => r.state.station_id).filter(Boolean)),
  ) as string[];
  const filtered =
    station === "all" ? pending : pending.filter((r) => r.state.station_id === station);

  const selected = pending.find((r) => r.thread_id === selectedThreadId) ?? null;

  function openCase(run: GraphRun) {
    setSelectedThreadId(run.thread_id);
    setReason("");
    setValidationError("");
  }

  async function submit(action: "APPROVE" | "REJECT") {
    if (!selected) return;
    if (reason.trim().length < 4) {
      setValidationError("CẦN NHẬP LÝ DO TRƯỚC KHI XÁC NHẬN QUYẾT ĐỊNH");
      return;
    }
    if (!reviewer.trim()) {
      setValidationError("CẦN NHẬP TÊN GIÁM SÁT VIÊN");
      return;
    }
    setValidationError("");
    try {
      await resume.mutateAsync({
        threadId: selected.thread_id,
        payload: { action, reviewer: reviewer.trim(), reason: reason.trim() },
      });
      setSelectedThreadId(null);
    } catch {
      // resume.error is rendered below
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Hàng đợi leo thang"
        meta={[{ label: "Đang chờ", value: String(pending.length) }]}
        right={
          <Select
            label="Trạm"
            value={station}
            onChange={setStation}
            options={[
              { value: "all", label: "Tất cả" },
              ...stations.map((s) => ({ value: s, label: s })),
            ]}
          />
        }
      />

      <Panel dense>
        {runsQuery.isPending ? (
          <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
            Đang tải…
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            title="Không có đơn chuyển cấp nào đang chờ"
            description="Hàng đợi leo thang hiện đang trống."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Xe</Th>
                <Th>Trạm</Th>
                <Th>Loại lỗi</Th>
                <Th>Người chuyển cấp</Th>
                <Th>Đề xuất</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <Tr
                  key={r.thread_id}
                  onClick={() => openCase(r)}
                  active={r.thread_id === selectedThreadId}
                >
                  <Td className="num font-medium">{r.state.vehicle_id}</Td>
                  <Td>{r.state.station_id || "—"}</Td>
                  <Td>{r.state.defect_type || "—"}</Td>
                  <Td>{r.state.human_decision?.reviewer || "—"}</Td>
                  <Td className="max-w-[280px] truncate text-muted-foreground">
                    {r.state.human_decision?.recommendation || "—"}
                  </Td>
                  <Td>
                    <Badge tone="warn">CHỜ SUPERVISOR</Badge>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <Drawer
        open={!!selected}
        onClose={() => setSelectedThreadId(null)}
        title={selected ? `${selected.state.vehicle_id} · #${selected.state.inspection_id}` : ""}
        subtitle={
          selected ? `Trạm ${selected.state.station_id || "—"} · ${selected.state.zone_name}` : ""
        }
        width="max-w-[680px]"
      >
        {selected && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
              <Field label="Model xe">{selected.state.vehicle_model}</Field>
              <Field label="Loại lỗi">{selected.state.defect_type || "—"}</Field>
              <Field label="Mức độ">{selected.state.severity || "—"}</Field>
              <Field label="Thread" mono>
                {selected.thread_id}
              </Field>
            </div>

            <Panel title="Yêu cầu chuyển cấp từ QC Inspector">
              <div className="space-y-2 text-[12.5px] text-foreground">
                <div>
                  <span className="label-caps mr-1.5">Người xét duyệt</span>
                  {selected.state.human_decision?.reviewer || "—"}
                </div>
                <div>
                  <span className="label-caps mr-1.5">Lý do</span>
                  {selected.state.human_decision?.reason || "—"}
                </div>
                <div>
                  <span className="label-caps mr-1.5">Đề xuất ghi đè</span>
                  {selected.state.human_decision?.recommendation || "—"}
                </div>
              </div>
            </Panel>

            <div className="space-y-3 rounded-sm border border-border bg-surface-2 p-3">
              <div className="label-caps">Quyết định của Supervisor</div>
              <TextField label="Giám sát viên" value={reviewer} onChange={setReviewer} />
              <TextArea
                label="Lý do (bắt buộc)"
                value={reason}
                onChange={setReason}
                placeholder="Đồng ý ghi đè theo đề xuất vì..."
              />
              {validationError ? (
                <p className="font-mono text-[11px] text-destructive">{validationError}</p>
              ) : null}
              {resume.isError ? (
                <p className="font-mono text-[11px] text-destructive">
                  {resume.error instanceof Error ? resume.error.message : "Gửi quyết định thất bại."}
                </p>
              ) : null}
              <div className="grid grid-cols-2 gap-2">
                <Btn
                  variant="danger"
                  disabled={resume.isPending}
                  onClick={() => void submit("REJECT")}
                  className="h-9 justify-center"
                >
                  <XCircle className="size-4" /> TỪ CHỐI CHUYỂN CẤP
                </Btn>
                <Btn
                  variant="success"
                  disabled={resume.isPending}
                  onClick={() => void submit("APPROVE")}
                  className="h-9 justify-center"
                >
                  <CheckCircle2 className="size-4" /> PHÊ DUYỆT
                </Btn>
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
