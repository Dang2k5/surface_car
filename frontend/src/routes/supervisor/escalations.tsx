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
import { formatAffectedZones } from "@/lib/detection-geometry";
import { useAgentRuns, usePolicyCatalog, useResumeInspection } from "@/lib/queries";
import type { GraphRun, PolicyCatalog, PolicyCatalogItem } from "@/lib/api-types";

const UPHOLD_POLICY = "UPHOLD_POLICY";

function isPolicyApproved(catalog: PolicyCatalog | undefined, policy: PolicyCatalogItem): boolean {
  return (policy.checklist_status || catalog?.status) === "APPROVED";
}

/** Policies a supervisor may legitimately apply to THIS case. Mirrors the EXACT eligibility
 * check the graph performs server-side (agent/services/policy.py's list_approved_policies,
 * used by agent/graph/nodes.py's supervisor_review to build allowed_policy_ids) so the
 * dropdown never hides something the resume call would actually accept, nor offers something
 * it would reject. That server check is APPROVED-status only — it does NOT filter by
 * defect_type (a supervisor override may legitimately apply any approved policy, not just one
 * scoped to this case's own defect type) — do not reintroduce a defect_type filter here. */
function eligiblePoliciesFor(catalog: PolicyCatalog | undefined, _run: GraphRun): PolicyCatalogItem[] {
  return (catalog?.policies ?? []).filter((p) => isPolicyApproved(catalog, p));
}

export const Route = createFileRoute("/supervisor/escalations")({
  head: () => ({
    meta: [{ title: "Hàng đợi leo thang — QC Supervisor" }],
  }),
  component: Escalations,
});

/** A case has passed the operator's own review (human_decision set) and is still
 * INTERRUPTED only when it's paused a second time at supervisor_review — i.e. the
 * operator chose "CHUYỂN CẤP XÉT DUYỆT" (OVERRIDE) and it now needs a supervisor to either
 * uphold the automated policy or apply one specific approved policy
 * (agent/graph/nodes.py's supervisor_review, backend/app/langgraph_api.py). */
function isPendingSupervisor(run: GraphRun): boolean {
  return run.status === "INTERRUPTED" && !!run.state.human_decision;
}

function waitMinutes(run: GraphRun): number {
  const at = run.state._persisted_at ? Date.parse(run.state._persisted_at) : NaN;
  if (Number.isNaN(at)) return 0;
  return Math.max(0, Math.round((Date.now() - at) / 60_000));
}

function formatWait(minutes: number): string {
  if (minutes < 60) return `${minutes} phút`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `${hours} giờ${rest ? ` ${rest} phút` : ""}`;
}

function waitTone(minutes: number): "pass" | "warn" | "fail" {
  if (minutes >= 120) return "fail";
  if (minutes >= 30) return "warn";
  return "pass";
}

function Escalations() {
  const runsQuery = useAgentRuns();
  const catalogQuery = usePolicyCatalog();
  const { profile } = useAuth();
  const resume = useResumeInspection();

  const [station, setStation] = useState("all");
  const [severity, setSeverity] = useState("all");
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [reason, setReason] = useState("");
  const [appliedPolicyId, setAppliedPolicyId] = useState("");
  const [validationError, setValidationError] = useState("");

  useEffect(() => {
    if (profile) setReviewer((current) => current || profileDisplayName(profile));
  }, [profile]);

  const pending = (runsQuery.data ?? []).filter(isPendingSupervisor);
  const stations = Array.from(
    new Set(pending.map((r) => r.state.station_id).filter(Boolean)),
  ) as string[];
  const severities = Array.from(
    new Set(pending.map((r) => r.state.severity).filter(Boolean)),
  ) as string[];

  const filtered = pending
    .filter((r) => station === "all" || r.state.station_id === station)
    .filter((r) => severity === "all" || r.state.severity === severity)
    .sort((a, b) => waitMinutes(b) - waitMinutes(a));

  const selected = pending.find((r) => r.thread_id === selectedThreadId) ?? null;
  const longestWaitMinutes = filtered[0] ? waitMinutes(filtered[0]) : 0;

  function openCase(run: GraphRun) {
    setSelectedThreadId(run.thread_id);
    setReason("");
    setAppliedPolicyId("");
    setValidationError("");
  }

  const eligiblePolicies = selected ? eligiblePoliciesFor(catalogQuery.data, selected) : [];

  async function submit(action: string) {
    if (!selected) return;
    if (reason.trim().length < 4) {
      setValidationError("CẦN NHẬP LÝ DO TRƯỚC KHI XÁC NHẬN QUYẾT ĐỊNH");
      return;
    }
    if (!reviewer.trim()) {
      setValidationError("CẦN NHẬP TÊN GIÁM SÁT VIÊN");
      return;
    }
    if (action !== UPHOLD_POLICY && !eligiblePolicies.some((p) => p.id === action)) {
      setValidationError("CẦN CHỌN MỘT CHÍNH SÁCH ĐÃ PHÊ DUYỆT ĐỂ ÁP DỤNG");
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
        meta={[
          { label: "Đang chờ", value: String(pending.length) },
          { label: "Chờ lâu nhất", value: pending.length ? formatWait(longestWaitMinutes) : "—" },
        ]}
        right={
          <div className="flex items-end gap-2">
            <Select
              label="Trạm"
              value={station}
              onChange={setStation}
              options={[
                { value: "all", label: "Tất cả" },
                ...stations.map((s) => ({ value: s, label: s })),
              ]}
            />
            <Select
              label="Mức độ"
              value={severity}
              onChange={setSeverity}
              options={[
                { value: "all", label: "Tất cả" },
                ...severities.map((s) => ({ value: s, label: s })),
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
            title="Không có đơn chuyển cấp nào đang chờ"
            description="Hàng đợi leo thang hiện đang trống."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Xe</Th>
                <Th>Trạm</Th>
                <Th>Mức độ</Th>
                <Th>Loại lỗi</Th>
                <Th>Người chuyển cấp</Th>
                <Th>Đề xuất</Th>
                <Th>Thời gian chờ</Th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => {
                const minutes = waitMinutes(r);
                return (
                  <Tr
                    key={r.thread_id}
                    onClick={() => openCase(r)}
                    active={r.thread_id === selectedThreadId}
                  >
                    <Td className="num font-medium">{r.state.vehicle_id}</Td>
                    <Td>{r.state.station_id || "—"}</Td>
                    <Td>{r.state.severity || "—"}</Td>
                    <Td>{r.state.defect_type || "—"}</Td>
                    <Td>{r.state.human_decision?.reviewer || "—"}</Td>
                    <Td className="max-w-[220px] truncate text-muted-foreground">
                      {r.state.human_decision?.recommendation || "—"}
                    </Td>
                    <Td>
                      <Badge tone={waitTone(minutes)}>{formatWait(minutes)}</Badge>
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
        onClose={() => setSelectedThreadId(null)}
        title={selected ? `${selected.state.vehicle_id} · #${selected.state.inspection_id}` : ""}
        subtitle={
          selected
            ? `Trạm ${selected.state.station_id || "—"} · ${formatAffectedZones(selected.state.affected_zones)}`
            : ""
        }
        width="max-w-[680px]"
      >
        {selected && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
              <Field label="Model xe">{selected.state.vehicle_model}</Field>
              <Field label="Loại lỗi">{selected.state.defect_type || "—"}</Field>
              <Field label="Mức độ">{selected.state.severity || "—"}</Field>
              <Field label="Thời gian chờ">{formatWait(waitMinutes(selected))}</Field>
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
              <Select
                label="Chính sách áp dụng nếu duyệt theo đề xuất"
                value={appliedPolicyId}
                onChange={setAppliedPolicyId}
                options={[
                  { value: "", label: "— Chọn chính sách đã phê duyệt —" },
                  ...eligiblePolicies.map((p) => ({
                    value: p.id,
                    label: `${p.title} · ${p.final_status}`,
                  })),
                ]}
              />
              {eligiblePolicies.length === 0 ? (
                <p className="font-mono text-[11px] text-muted-foreground">
                  Không có chính sách đã phê duyệt nào khớp loại lỗi này — chỉ có thể giữ nguyên
                  chính sách gốc.
                </p>
              ) : null}
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
                  onClick={() => void submit(UPHOLD_POLICY)}
                  className="h-9 justify-center"
                >
                  <XCircle className="size-4" /> GIỮ CHÍNH SÁCH GỐC
                </Btn>
                <Btn
                  variant="success"
                  disabled={resume.isPending || !appliedPolicyId}
                  onClick={() => void submit(appliedPolicyId)}
                  className="h-9 justify-center"
                >
                  <CheckCircle2 className="size-4" /> ÁP DỤNG CHÍNH SÁCH
                </Btn>
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
