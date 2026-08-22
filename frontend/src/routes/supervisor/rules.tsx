import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Plus } from "lucide-react";
import {
  Badge,
  Btn,
  Checkbox,
  Drawer,
  EmptyState,
  Field,
  PageHeader,
  Panel,
  Select,
  TextArea,
  TextField,
} from "@/components/supervisor/ui";
import {
  useCreatePolicy,
  useDeletePolicy,
  usePolicyCatalog,
  useUpdatePolicy,
} from "@/lib/queries";
import type { PolicyCatalogItem, PolicyItemCreate } from "@/lib/api-types";
import {
  actionCodeLabel,
  checklistStatusLabel,
  defectTypeLabel,
  documentStatusLabel,
  evidenceLabel,
  finalStatusLabel,
  stepLabel,
} from "@/lib/policy-i18n";

function actionCodesOf(p: PolicyCatalogItem): string[] {
  if (p.action_code) return [p.action_code];
  if (p.action_code_by_defect) return Object.values(p.action_code_by_defect);
  return [];
}

export const Route = createFileRoute("/supervisor/rules")({
  head: () => ({
    meta: [{ title: "Chính sách QC — QC Supervisor" }],
  }),
  component: Rules,
});

const csv = (v: string) =>
  v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

const lines = (v: string) =>
  v
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

type FormState = {
  id: string;
  title: string;
  vehicleModels: string;
  conditions: string;
  checklistStatus: "DRAFT" | "APPROVED";
  defectTypes: string;
  actionMode: "single" | "byDefect";
  actionCode: string;
  actionCodeByDefect: string;
  finalStatus: string;
  testDriveAllowed: "yes" | "no" | "unknown";
  humanRequired: boolean;
  requiredEvidence: string;
  steps: string;
  sourceIds: string[];
};

const emptyForm: FormState = {
  id: "",
  title: "",
  vehicleModels: "*",
  conditions: "",
  checklistStatus: "DRAFT",
  defectTypes: "",
  actionMode: "single",
  actionCode: "",
  actionCodeByDefect: "",
  finalStatus: "",
  testDriveAllowed: "unknown",
  humanRequired: false,
  requiredEvidence: "",
  steps: "",
  sourceIds: [],
};

function formFromPolicy(p: PolicyCatalogItem): FormState {
  return {
    id: p.id,
    title: p.title,
    vehicleModels: (p.applicability?.vehicle_models ?? ["*"]).join(", "),
    conditions: p.conditions.join("\n"),
    checklistStatus: p.checklist_status === "APPROVED" ? "APPROVED" : "DRAFT",
    defectTypes: p.defect_types.join(", "),
    actionMode: p.action_code_by_defect ? "byDefect" : "single",
    actionCode: p.action_code ?? "",
    actionCodeByDefect: Object.entries(p.action_code_by_defect ?? {})
      .map(([k, v]) => `${k}=${v}`)
      .join("\n"),
    finalStatus: p.final_status,
    testDriveAllowed:
      p.test_drive_allowed === true ? "yes" : p.test_drive_allowed === false ? "no" : "unknown",
    humanRequired: p.human_required,
    requiredEvidence: p.required_evidence.join(", "),
    steps: p.steps.join("\n"),
    sourceIds: p.source_ids,
  };
}

function payloadFromForm(form: FormState): PolicyItemCreate {
  const actionCodeByDefect: Record<string, string> = {};
  if (form.actionMode === "byDefect") {
    for (const line of lines(form.actionCodeByDefect)) {
      const [defect, code] = line.split("=").map((s) => s.trim());
      if (defect && code) actionCodeByDefect[defect] = code;
    }
  }
  return {
    id: form.id.trim().toUpperCase(),
    title: form.title.trim(),
    applicability: { vehicle_models: csv(form.vehicleModels).length ? csv(form.vehicleModels) : ["*"] },
    conditions: lines(form.conditions),
    checklist_status: form.checklistStatus,
    defect_types: csv(form.defectTypes),
    ...(form.actionMode === "single"
      ? { action_code: form.actionCode.trim() }
      : { action_code_by_defect: actionCodeByDefect }),
    final_status: form.finalStatus.trim(),
    test_drive_allowed:
      form.testDriveAllowed === "yes" ? true : form.testDriveAllowed === "no" ? false : null,
    human_required: form.humanRequired,
    required_evidence: csv(form.requiredEvidence),
    steps: lines(form.steps),
    source_ids: form.sourceIds,
  };
}

function Rules() {
  const catalogQuery = usePolicyCatalog();
  const createPolicy = useCreatePolicy();
  const updatePolicy = useUpdatePolicy();
  const deletePolicy = useDeletePolicy();

  const [selected, setSelected] = useState<PolicyCatalogItem | null>(null);
  const [editing, setEditing] = useState<FormState | null>(null);
  const [creating, setCreating] = useState<FormState | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const catalog = catalogQuery.data;
  const sourceById = new Map((catalog?.sources ?? []).map((s) => [s.id, s]));

  const form = creating ?? editing;
  const isCreateMode = !!creating;

  function closeForm() {
    setCreating(null);
    setEditing(null);
    setFormError(null);
  }

  function submitForm() {
    if (!form) return;
    setFormError(null);
    const payload = payloadFromForm(form);
    if (!payload.id || !payload.title || payload.defect_types.length === 0 || !payload.final_status) {
      setFormError("Vui lòng nhập đầy đủ Mã policy, Tiêu đề, Loại lỗi áp dụng và Trạng thái cuối.");
      return;
    }
    if (form.actionMode === "single" && !payload.action_code) {
      setFormError("Vui lòng nhập Action code.");
      return;
    }
    if (form.actionMode === "byDefect" && !Object.keys(payload.action_code_by_defect ?? {}).length) {
      setFormError("Vui lòng khai báo ít nhất 1 dòng action_code theo loại lỗi.");
      return;
    }

    if (isCreateMode) {
      createPolicy.mutate(payload, {
        onSuccess: () => closeForm(),
        onError: (e) => setFormError(e instanceof Error ? e.message : "Tạo policy thất bại."),
      });
    } else if (editing) {
      const { id, ...changes } = payload;
      updatePolicy.mutate(
        { policyId: editing.id, payload: changes },
        {
          onSuccess: () => {
            closeForm();
            setSelected(null);
          },
          onError: (e) => setFormError(e instanceof Error ? e.message : "Cập nhật policy thất bại."),
        },
      );
    }
  }

  function handleDelete(policyId: string) {
    deletePolicy.mutate(policyId, {
      onSuccess: () => setSelected(null),
    });
  }

  const toggleSource = (id: string) => {
    if (!form) return;
    const next = form.sourceIds.includes(id)
      ? form.sourceIds.filter((s) => s !== id)
      : [...form.sourceIds, id];
    if (isCreateMode) setCreating({ ...form, sourceIds: next });
    else setEditing({ ...form, sourceIds: next });
  };

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    if (isCreateMode && creating) setCreating({ ...creating, [key]: value });
    else if (editing) setEditing({ ...editing, [key]: value });
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Chính sách QC"
        description="Danh mục chính sách xử lý lỗi đang áp dụng cho AI Engine (GET/POST/PATCH/DELETE /api/policies)."
        meta={
          catalog
            ? [
                { label: "Revision", value: catalog.revision },
                { label: "Trạng thái", value: catalog.status },
                { label: "Phạm vi duyệt", value: catalog.approval_scope },
                { label: "Chủ sở hữu", value: catalog.owner },
              ]
            : []
        }
        right={
          <Btn
            variant="solid"
            onClick={() => {
              setSelected(null);
              setEditing(null);
              setCreating(emptyForm);
              setFormError(null);
            }}
          >
            <Plus className="size-3.5" /> Thêm chính sách
          </Btn>
        }
      />

      {catalog?.disclaimer ? (
        <div className="rounded-sm border border-warning/35 bg-warning/10 px-3 py-2 text-[12px] leading-relaxed text-warning">
          {catalog.disclaimer}
        </div>
      ) : null}

      {catalogQuery.isPending ? (
        <Panel>
          <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
            Đang tải…
          </div>
        </Panel>
      ) : !catalog || catalog.policies.length === 0 ? (
        <Panel>
          <EmptyState
            title="Chưa có chính sách nào"
            description="Danh mục chính sách hiện đang trống. Bấm “Thêm chính sách” để tạo mới."
          />
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {catalog.policies.map((p) => (
            <button
              key={p.id}
              onClick={() => setSelected(p)}
              className="panel flex flex-col gap-2 p-4 text-left transition-colors hover:border-border-strong"
            >
              <div className="flex items-center gap-2">
                <span className="num text-[11px] text-muted-foreground">{p.id}</span>
                <Badge tone={p.checklist_status === "APPROVED" ? "pass" : "warn"}>
                  {checklistStatusLabel(p.checklist_status)}
                </Badge>
                {p.human_required ? <Badge tone="info">Cần con người</Badge> : null}
              </div>
              <div className="text-[13px] font-semibold">{p.title}</div>
              <div className="flex flex-wrap gap-1.5">
                {p.defect_types.map((d) => (
                  <Badge key={d} tone="neutral">
                    {defectTypeLabel(d)}
                  </Badge>
                ))}
              </div>
              <div className="text-[11px] text-muted-foreground">
                Kết quả: <span className="text-foreground">{finalStatusLabel(p.final_status)}</span>
                {" · "}
                Test drive:{" "}
                <span className="num text-foreground">
                  {p.test_drive_allowed ? "Cho phép" : "Không"}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* -------------------------------------------------- Detail drawer */}
      <Drawer
        open={!!selected && !editing}
        onClose={() => setSelected(null)}
        title={selected ? selected.title : ""}
        subtitle={selected ? selected.id : ""}
        width="max-w-[720px]"
      >
        {selected && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={selected.checklist_status === "APPROVED" ? "pass" : "warn"}>
                  {checklistStatusLabel(selected.checklist_status)}
                </Badge>
                {actionCodesOf(selected).map((code) => (
                  <Badge key={code} tone="neutral">
                    {actionCodeLabel(code)}
                  </Badge>
                ))}
                {selected.human_required ? <Badge tone="info">Cần con người xác nhận</Badge> : null}
              </div>
              <div className="flex shrink-0 gap-1.5">
                <Btn variant="outline" onClick={() => setEditing(formFromPolicy(selected))}>
                  Sửa
                </Btn>
                <Btn variant="danger" onClick={() => handleDelete(selected.id)}>
                  Xoá
                </Btn>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
              <Field label="Áp dụng cho lỗi">
                {selected.defect_types.map(defectTypeLabel).join(", ")}
              </Field>
              <Field label="Trạng thái cuối">{finalStatusLabel(selected.final_status)}</Field>
              <Field label="Test drive">
                {selected.test_drive_allowed ? "Cho phép" : "Không cho phép"}
              </Field>
              <Field label="Model xe áp dụng">
                {selected.applicability.vehicle_models.join(", ") || "Tất cả"}
              </Field>
            </div>

            {selected.conditions.length > 0 ? (
              <Panel title="Điều kiện áp dụng">
                <ul className="list-disc space-y-1 pl-4 text-[12.5px] text-foreground">
                  {selected.conditions.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </Panel>
            ) : null}

            {selected.required_evidence.length > 0 ? (
              <Panel title="Bằng chứng bắt buộc">
                <div className="flex flex-wrap gap-1.5">
                  {selected.required_evidence.map((e) => (
                    <Badge key={e} tone="warn">
                      {evidenceLabel(e)}
                    </Badge>
                  ))}
                </div>
              </Panel>
            ) : null}

            {selected.steps.length > 0 ? (
              <Panel title="Quy trình xử lý">
                <ol className="list-decimal space-y-1 pl-4 text-[12.5px] text-foreground">
                  {selected.steps.map((s, i) => (
                    <li key={i}>{stepLabel(s)}</li>
                  ))}
                </ol>
              </Panel>
            ) : null}

            {selected.source_ids.length > 0 ? (
              <Panel title="Tài liệu tham chiếu">
                <ul className="space-y-2">
                  {selected.source_ids.map((id) => {
                    const source = sourceById.get(id);
                    if (!source) return null;
                    return (
                      <li key={id} className="text-[12px]">
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-info hover:underline"
                        >
                          {source.title}
                        </a>
                        <div className="text-[11px] text-muted-foreground">
                          {source.document_family} {source.revision} ·{" "}
                          {documentStatusLabel(source.document_status)}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </Panel>
            ) : null}
          </div>
        )}
      </Drawer>

      {/* -------------------------------------------------- Create/edit drawer */}
      <Drawer
        open={!!form}
        onClose={closeForm}
        title={isCreateMode ? "Thêm chính sách mới" : `Sửa · ${editing?.id}`}
        subtitle="Mọi thay đổi ghi trực tiếp vào agent/policies/qc_policy_catalog.json và có hiệu lực ngay với AI Engine."
        width="max-w-[720px]"
      >
        {form && (
          <div className="space-y-4">
            {formError && (
              <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
                {formError}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <TextField
                label="Mã policy (id)"
                value={form.id}
                onChange={(v) => setField("id", v)}
                placeholder="FNS-EXAMPLE-001"
                mono
              />
              <Select
                label="Trạng thái checklist"
                value={form.checklistStatus}
                onChange={(v) => setField("checklistStatus", v as "DRAFT" | "APPROVED")}
                options={[
                  { value: "DRAFT", label: "DRAFT" },
                  { value: "APPROVED", label: "APPROVED" },
                ]}
              />
            </div>

            <TextField
              label="Tiêu đề"
              value={form.title}
              onChange={(v) => setField("title", v)}
              placeholder="Tiêu đề chính sách"
            />

            <div className="grid grid-cols-2 gap-3">
              <TextField
                label="Loại lỗi áp dụng (phân cách bởi dấu phẩy)"
                value={form.defectTypes}
                onChange={(v) => setField("defectTypes", v)}
                placeholder="scratch, dent"
              />
              <TextField
                label="Model xe áp dụng (phân cách bởi dấu phẩy, * = tất cả)"
                value={form.vehicleModels}
                onChange={(v) => setField("vehicleModels", v)}
                placeholder="*"
              />
            </div>

            <TextArea
              label="Điều kiện áp dụng (mỗi dòng 1 điều kiện)"
              value={form.conditions}
              onChange={(v) => setField("conditions", v)}
              rows={3}
            />

            <div className="grid grid-cols-2 gap-3">
              <Select
                label="Kiểu action"
                value={form.actionMode}
                onChange={(v) => setField("actionMode", v as "single" | "byDefect")}
                options={[
                  { value: "single", label: "1 action code cho toàn bộ" },
                  { value: "byDefect", label: "Action code riêng theo loại lỗi" },
                ]}
              />
              <TextField
                label="Trạng thái cuối (final_status)"
                value={form.finalStatus}
                onChange={(v) => setField("finalStatus", v)}
                placeholder="HOLD_FOR_QC"
                mono
              />
            </div>

            {form.actionMode === "single" ? (
              <TextField
                label="Action code"
                value={form.actionCode}
                onChange={(v) => setField("actionCode", v)}
                placeholder="MANUAL_VISUAL_REINSPECTION"
                mono
              />
            ) : (
              <TextArea
                label="Action code theo loại lỗi (mỗi dòng: loai_loi=ACTION_CODE)"
                value={form.actionCodeByDefect}
                onChange={(v) => setField("actionCodeByDefect", v)}
                rows={3}
                hint="Ví dụ: glass_shatter=ISOLATE_FOR_GLASS_REPAIR"
              />
            )}

            <div className="grid grid-cols-2 gap-3">
              <Select
                label="Cho phép test drive"
                value={form.testDriveAllowed}
                onChange={(v) => setField("testDriveAllowed", v as "yes" | "no" | "unknown")}
                options={[
                  { value: "unknown", label: "Chưa xác định" },
                  { value: "yes", label: "Cho phép" },
                  { value: "no", label: "Không cho phép" },
                ]}
              />
              <div className="flex items-end pb-1.5">
                <Checkbox
                  label="Bắt buộc con người xác nhận (human_required)"
                  checked={form.humanRequired}
                  onChange={(v) => setField("humanRequired", v)}
                />
              </div>
            </div>

            <TextField
              label="Bằng chứng bắt buộc (phân cách bởi dấu phẩy)"
              value={form.requiredEvidence}
              onChange={(v) => setField("requiredEvidence", v)}
              placeholder="controlled_light_reinspection, defect_extent_measurement"
            />

            <TextArea
              label="Quy trình xử lý (mỗi dòng 1 bước)"
              value={form.steps}
              onChange={(v) => setField("steps", v)}
              rows={3}
            />

            {catalog && catalog.sources.length > 0 ? (
              <Panel title="Tài liệu tham chiếu" dense bodyClassName="max-h-52 overflow-y-auto p-3 space-y-1.5">
                {catalog.sources.map((s) => (
                  <Checkbox
                    key={s.id}
                    label={`${s.title} (${s.document_family} ${s.revision})`}
                    checked={form.sourceIds.includes(s.id)}
                    onChange={() => toggleSource(s.id)}
                  />
                ))}
              </Panel>
            ) : null}

            <div className="flex justify-end gap-2 border-t border-border pt-3">
              <Btn variant="outline" onClick={closeForm}>
                Huỷ
              </Btn>
              <Btn
                variant="solid"
                onClick={submitForm}
                disabled={createPolicy.isPending || updatePolicy.isPending}
              >
                {isCreateMode ? "Tạo chính sách" : "Lưu thay đổi"}
              </Btn>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
