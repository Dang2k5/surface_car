import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useRef, useState } from "react";
import { Plus, Upload } from "lucide-react";
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
  useCreateSource,
  useDeletePolicy,
  useExtractPolicyDraft,
  usePolicyCatalog,
  useUpdatePolicy,
} from "@/lib/queries";
import type {
  PolicyCatalog,
  PolicyCatalogItem,
  PolicyExtractionResult,
  PolicyItemCreate,
} from "@/lib/api-types";
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
  defectTypes: string[];
  // Whether 1 action code covers every selected defect type or each defect type gets
  // its own is derived from defectTypes.length, not stored separately -- keeping both
  // maps around means nothing is lost when a checkbox is toggled on/off.
  actionCodeSingle: string;
  actionCodeByDefect: Record<string, string>;
  finalStatus: string;
  testDriveAllowed: "yes" | "no" | "unknown";
  humanRequired: boolean;
  requiredEvidence: string[];
  steps: string;
  sourceIds: string[];
};

// Core CV taxonomy this system currently detects. Extending to a new defect type
// (e.g. a future model class) only requires adding it here -- collectVocab below
// also folds in anything already used in the catalog, so a value introduced via
// AI-extraction or a manual JSON edit shows up automatically without a code change.
const DEFECT_TYPE_OPTIONS = ["scratch", "paint_defect", "dent", "crack", "*"];

const emptyForm: FormState = {
  id: "",
  title: "",
  vehicleModels: "*",
  conditions: "",
  checklistStatus: "DRAFT",
  defectTypes: [],
  actionCodeSingle: "",
  actionCodeByDefect: {},
  finalStatus: "FAIL",
  testDriveAllowed: "unknown",
  humanRequired: false,
  requiredEvidence: [],
  steps: "",
  sourceIds: [],
};

function collectVocab(
  catalog: PolicyCatalog | undefined,
  pick: (p: PolicyCatalogItem) => string[],
): string[] {
  const set = new Set<string>();
  for (const p of catalog?.policies ?? []) for (const v of pick(p)) set.add(v);
  return Array.from(set).sort();
}

function collectActionCodes(catalog: PolicyCatalog | undefined): string[] {
  const set = new Set<string>();
  for (const p of catalog?.policies ?? []) {
    if (p.action_code) set.add(p.action_code);
    for (const v of Object.values(p.action_code_by_defect ?? {})) set.add(v);
  }
  return Array.from(set).sort();
}

function slugId(text: string): string {
  const slug = text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  return slug || "DOC";
}

function formFromExtraction(draft: PolicyExtractionResult["policy_draft"]): FormState {
  return {
    id: draft.suggested_id,
    title: draft.title,
    vehicleModels: "*",
    conditions: draft.conditions.join("\n"),
    checklistStatus: "DRAFT",
    defectTypes: draft.defect_types,
    actionCodeSingle: draft.action_code,
    actionCodeByDefect: Object.fromEntries(draft.defect_types.map((dt) => [dt, draft.action_code])),
    finalStatus: draft.final_status,
    testDriveAllowed:
      draft.test_drive_allowed === true
        ? "yes"
        : draft.test_drive_allowed === false
          ? "no"
          : "unknown",
    humanRequired: draft.human_required,
    requiredEvidence: draft.required_evidence,
    steps: draft.steps.join("\n"),
    sourceIds: [],
  };
}

function formFromPolicy(p: PolicyCatalogItem): FormState {
  return {
    id: p.id,
    title: p.title,
    vehicleModels: (p.applicability?.vehicle_models ?? ["*"]).join(", "),
    conditions: p.conditions.join("\n"),
    checklistStatus: p.checklist_status === "APPROVED" ? "APPROVED" : "DRAFT",
    defectTypes: p.defect_types,
    actionCodeSingle: p.action_code ?? "",
    actionCodeByDefect: p.action_code_by_defect ?? {},
    finalStatus: p.final_status,
    testDriveAllowed:
      p.test_drive_allowed === true ? "yes" : p.test_drive_allowed === false ? "no" : "unknown",
    humanRequired: p.human_required,
    requiredEvidence: p.required_evidence,
    steps: p.steps.join("\n"),
    sourceIds: p.source_ids,
  };
}

function payloadFromForm(form: FormState): PolicyItemCreate {
  const singleAction = form.defectTypes.length <= 1;
  const actionCodeByDefect = Object.fromEntries(
    form.defectTypes
      .map((dt) => [dt, (form.actionCodeByDefect[dt] ?? "").trim()])
      .filter(([, code]) => code),
  );
  return {
    id: form.id.trim().toUpperCase(),
    title: form.title.trim(),
    applicability: {
      vehicle_models: csv(form.vehicleModels).length ? csv(form.vehicleModels) : ["*"],
    },
    conditions: lines(form.conditions),
    checklist_status: form.checklistStatus,
    defect_types: form.defectTypes,
    ...(singleAction
      ? { action_code: form.actionCodeSingle.trim() }
      : { action_code_by_defect: actionCodeByDefect }),
    final_status: form.finalStatus.trim(),
    test_drive_allowed:
      form.testDriveAllowed === "yes" ? true : form.testDriveAllowed === "no" ? false : null,
    human_required: form.humanRequired,
    required_evidence: form.requiredEvidence,
    steps: lines(form.steps),
    source_ids: form.sourceIds,
  };
}

function Rules() {
  const catalogQuery = usePolicyCatalog();
  const createPolicy = useCreatePolicy();
  const createSource = useCreateSource();
  const updatePolicy = useUpdatePolicy();
  const deletePolicy = useDeletePolicy();
  const extractPolicyDraft = useExtractPolicyDraft();

  const [selected, setSelected] = useState<PolicyCatalogItem | null>(null);
  const [editing, setEditing] = useState<FormState | null>(null);
  const [creating, setCreating] = useState<FormState | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [pendingSource, setPendingSource] = useState<
    (PolicyExtractionResult["source_draft"] & { id: string }) | null
  >(null);
  // Kept only in memory so the file is re-sent (and only then written to storage) at
  // save time -- see useCreateSource in @/lib/queries. Never uploaded on cancel.
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [extractionNotes, setExtractionNotes] = useState<string | null>(null);
  const [customEvidence, setCustomEvidence] = useState("");
  const [customDefectType, setCustomDefectType] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const catalog = catalogQuery.data;
  const sourceById = new Map((catalog?.sources ?? []).map((s) => [s.id, s]));

  const form = creating ?? editing;
  const isCreateMode = !!creating;

  const knownEvidence = useMemo(() => collectVocab(catalog, (p) => p.required_evidence), [catalog]);
  const evidenceOptions = useMemo(() => {
    const set = new Set(knownEvidence);
    for (const v of form?.requiredEvidence ?? []) set.add(v);
    return Array.from(set);
  }, [knownEvidence, form?.requiredEvidence]);

  const knownSteps = useMemo(() => collectVocab(catalog, (p) => p.steps), [catalog]);
  const stepLines = form ? lines(form.steps) : [];
  const stepSuggestions = knownSteps.filter((s) => !stepLines.includes(s));

  const knownDefectTypes = useMemo(() => collectVocab(catalog, (p) => p.defect_types), [catalog]);
  const defectTypeOptions = useMemo(() => {
    const set = new Set([...DEFECT_TYPE_OPTIONS, ...knownDefectTypes]);
    for (const v of form?.defectTypes ?? []) set.add(v);
    return Array.from(set);
  }, [knownDefectTypes, form?.defectTypes]);

  const knownActionCodes = useMemo(() => collectActionCodes(catalog), [catalog]);

  const knownVehicleModels = useMemo(
    () => collectVocab(catalog, (p) => p.applicability.vehicle_models).filter((m) => m !== "*"),
    [catalog],
  );

  const toggleDefectType = (value: string) => {
    if (!form) return;
    const adding = !form.defectTypes.includes(value);
    const nextDefectTypes = adding
      ? [...form.defectTypes, value]
      : form.defectTypes.filter((v) => v !== value);
    // Seed a new defect type's per-type action code from the single-action value so
    // switching between 1 and 2+ selected types never silently loses what was typed.
    const nextActionByDefect =
      adding && !(value in form.actionCodeByDefect)
        ? { ...form.actionCodeByDefect, [value]: form.actionCodeSingle }
        : form.actionCodeByDefect;
    if (isCreateMode && creating) {
      setCreating({
        ...creating,
        defectTypes: nextDefectTypes,
        actionCodeByDefect: nextActionByDefect,
      });
    } else if (editing) {
      setEditing({
        ...editing,
        defectTypes: nextDefectTypes,
        actionCodeByDefect: nextActionByDefect,
      });
    }
  };

  const addCustomDefectType = () => {
    const code = customDefectType.trim().toLowerCase().replace(/\s+/g, "_");
    if (!form || !code || form.defectTypes.includes(code)) return;
    toggleDefectType(code);
    setCustomDefectType("");
  };

  const setActionCodeForDefect = (defectType: string, code: string) => {
    if (!form) return;
    setField("actionCodeByDefect", { ...form.actionCodeByDefect, [defectType]: code });
  };

  const toggleEvidence = (value: string) => {
    if (!form) return;
    const next = form.requiredEvidence.includes(value)
      ? form.requiredEvidence.filter((v) => v !== value)
      : [...form.requiredEvidence, value];
    setField("requiredEvidence", next);
  };

  const addStep = (code: string) => {
    if (!form) return;
    setField("steps", [...lines(form.steps), code].join("\n"));
  };

  const addCustomEvidence = () => {
    const code = customEvidence.trim().toLowerCase().replace(/\s+/g, "_");
    if (!form || !code || form.requiredEvidence.includes(code)) return;
    setField("requiredEvidence", [...form.requiredEvidence, code]);
    setCustomEvidence("");
  };

  function closeForm() {
    setCreating(null);
    setEditing(null);
    setFormError(null);
    setPendingSource(null);
    setPendingFile(null);
    setExtractionNotes(null);
  }

  function handleFileSelected(file: File) {
    setFormError(null);
    extractPolicyDraft.mutate(file, {
      onSuccess: (result) => {
        setSelected(null);
        setEditing(null);
        setCreating(formFromExtraction(result.policy_draft));
        setPendingSource({ ...result.source_draft, id: slugId(result.source_draft.title) });
        setPendingFile(file);
        setExtractionNotes(result.extraction_notes_vi || null);
      },
      onError: (e) =>
        setFormError(e instanceof Error ? e.message : "Trích xuất tài liệu thất bại."),
    });
  }

  function submitForm() {
    if (!form) return;
    setFormError(null);
    const payload = payloadFromForm(form);
    if (
      !payload.id ||
      !payload.title ||
      payload.defect_types.length === 0 ||
      !payload.final_status
    ) {
      setFormError(
        "Vui lòng nhập đầy đủ Mã chính sách, Tiêu đề, Loại lỗi áp dụng và Trạng thái cuối.",
      );
      return;
    }
    if (form.defectTypes.length <= 1 && !payload.action_code) {
      setFormError("Vui lòng nhập Hành động xử lý.");
      return;
    }
    if (
      form.defectTypes.length > 1 &&
      Object.keys(payload.action_code_by_defect ?? {}).length < form.defectTypes.length
    ) {
      setFormError("Vui lòng nhập Hành động xử lý cho từng loại lỗi đã chọn.");
      return;
    }
    if (pendingSource && !pendingSource.id.trim()) {
      setFormError("Vui lòng nhập Mã tài liệu nguồn.");
      return;
    }

    if (isCreateMode && pendingSource) {
      if (!pendingFile) {
        setFormError("Thiếu file tài liệu gốc — vui lòng upload lại.");
        return;
      }
      createSource.mutate(
        { file: pendingFile, fields: pendingSource },
        {
          onSuccess: (createdSource) => {
            createPolicy.mutate(
              { ...payload, source_ids: [...(payload.source_ids ?? []), createdSource.id] },
              {
                onSuccess: () => closeForm(),
                onError: (e) =>
                  setFormError(e instanceof Error ? e.message : "Tạo chính sách thất bại."),
              },
            );
          },
          onError: (e) =>
            setFormError(e instanceof Error ? e.message : "Đăng ký tài liệu nguồn thất bại."),
        },
      );
    } else if (isCreateMode) {
      createPolicy.mutate(payload, {
        onSuccess: () => closeForm(),
        onError: (e) => setFormError(e instanceof Error ? e.message : "Tạo chính sách thất bại."),
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
          onError: (e) =>
            setFormError(e instanceof Error ? e.message : "Cập nhật chính sách thất bại."),
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
          <div className="flex gap-1.5">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) handleFileSelected(file);
              }}
            />
            <Btn
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={extractPolicyDraft.isPending}
            >
              <Upload className="size-3.5" />
              {extractPolicyDraft.isPending
                ? "Đang trích xuất…"
                : "Upload tài liệu (AI trích xuất)"}
            </Btn>
            <Btn
              variant="solid"
              onClick={() => {
                setSelected(null);
                setEditing(null);
                setCreating(emptyForm);
                setFormError(null);
                setPendingSource(null);
                setExtractionNotes(null);
              }}
            >
              <Plus className="size-3.5" /> Thêm chính sách
            </Btn>
          </div>
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
                Chạy thử:{" "}
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
              <Field label="Chạy thử">
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
        subtitle="Có hiệu lực ngay sau khi lưu"
        width="max-w-[720px]"
      >
        {form && (
          <div className="space-y-4">
            {formError && (
              <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
                {formError}
              </div>
            )}

            {pendingSource && (
              <Panel title="Tài liệu nguồn (AI trích xuất)" dense bodyClassName="p-3 space-y-2">
                {extractionNotes && (
                  <div className="rounded-sm border border-info/35 bg-info/10 px-2.5 py-2 text-[11.5px] leading-relaxed text-info">
                    {extractionNotes}
                  </div>
                )}
                <TextField
                  label="Mã tài liệu nguồn"
                  value={pendingSource.id}
                  onChange={(v) =>
                    setPendingSource({ ...pendingSource, id: v.trim().toUpperCase() })
                  }
                  mono
                />
                <div className="truncate text-[11px] text-muted-foreground">
                  {pendingSource.title} · {pendingSource.document_family} {pendingSource.revision}
                </div>
              </Panel>
            )}

            <div className="grid grid-cols-2 gap-3">
              <TextField
                label="Mã chính sách"
                value={form.id}
                onChange={(v) => setField("id", v)}
                placeholder="FNS-EXAMPLE-001"
                mono
              />
              <div className="flex min-w-0 flex-col gap-1">
                <Select
                  label="Trạng thái phê duyệt"
                  value={form.checklistStatus}
                  onChange={(v) => setField("checklistStatus", v as "DRAFT" | "APPROVED")}
                  options={[
                    { value: "DRAFT", label: checklistStatusLabel("DRAFT") },
                    { value: "APPROVED", label: checklistStatusLabel("APPROVED") },
                  ]}
                />
                <span className="text-[11px] text-muted-foreground">
                  {form.checklistStatus === "DRAFT"
                    ? "Bản nháp: chưa áp dụng cho xe thật."
                    : "Đã duyệt: áp dụng ngay cho xe thật."}
                </span>
              </div>
            </div>

            <TextField
              label="Tiêu đề"
              value={form.title}
              onChange={(v) => setField("title", v)}
              placeholder="Tiêu đề chính sách"
            />

            <div className="grid grid-cols-2 gap-3">
              <div className="flex min-w-0 flex-col gap-1.5">
                <span className="label-caps">Loại lỗi áp dụng</span>
                <div className="flex flex-wrap gap-x-3 gap-y-1.5">
                  {defectTypeOptions.map((code) => (
                    <Checkbox
                      key={code}
                      label={defectTypeLabel(code)}
                      checked={form.defectTypes.includes(code)}
                      onChange={() => toggleDefectType(code)}
                    />
                  ))}
                </div>
                <div className="flex items-center gap-1.5">
                  <input
                    value={customDefectType}
                    onChange={(e) => setCustomDefectType(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addCustomDefectType();
                      }
                    }}
                    placeholder="Loại lỗi khác…"
                    className="h-7 min-w-0 flex-1 rounded-sm border border-border bg-surface-2 px-2 text-[12.5px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-ring"
                  />
                  <Btn variant="outline" size="xs" onClick={addCustomDefectType}>
                    Thêm
                  </Btn>
                </div>
              </div>
              <div className="flex min-w-0 flex-col gap-1.5">
                <span className="label-caps">Model xe áp dụng</span>
                <Checkbox
                  label="Tất cả model"
                  checked={form.vehicleModels.trim() === "*"}
                  onChange={(checked) => setField("vehicleModels", checked ? "*" : "")}
                />
                {form.vehicleModels.trim() !== "*" && (
                  <TextField
                    label="Model cụ thể"
                    value={form.vehicleModels}
                    onChange={(v) => setField("vehicleModels", v)}
                    placeholder="SUV_EV_2026, SEDAN_2025"
                    list="known-vehicle-models"
                  />
                )}
              </div>
            </div>
            <datalist id="known-vehicle-models">
              {knownVehicleModels.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>

            <TextArea
              label="Điều kiện bổ sung"
              value={form.conditions}
              onChange={(v) => setField("conditions", v)}
              rows={3}
              placeholder={
                "Mỗi dòng 1 điều kiện khác — không cần lặp lại loại lỗi. Ví dụ:\n" +
                "Phải đo được mức độ lỗi\nPhải có tiêu chí OEM đã phê duyệt"
              }
            />

            <Select
              label="Trạng thái cuối"
              value={form.finalStatus}
              onChange={(v) => setField("finalStatus", v)}
              options={[
                { value: "FAIL", label: finalStatusLabel("FAIL") },
                { value: "PASS", label: finalStatusLabel("PASS") },
                { value: "QUALITY_ALERT_OPEN", label: finalStatusLabel("QUALITY_ALERT_OPEN") },
              ]}
            />

            {form.defectTypes.length <= 1 ? (
              <TextField
                label="Hành động xử lý"
                value={form.actionCodeSingle}
                onChange={(v) => setField("actionCodeSingle", v)}
                placeholder="MANUAL_VISUAL_REINSPECTION"
                list="known-action-codes"
                mono
              />
            ) : (
              <div className="flex min-w-0 flex-col gap-2">
                <span className="label-caps">Hành động xử lý theo từng loại lỗi</span>
                {form.defectTypes.map((dt) => (
                  <TextField
                    key={dt}
                    label={defectTypeLabel(dt)}
                    value={form.actionCodeByDefect[dt] ?? ""}
                    onChange={(v) => setActionCodeForDefect(dt, v)}
                    placeholder="ACTION_CODE"
                    list="known-action-codes"
                    mono
                  />
                ))}
              </div>
            )}
            <datalist id="known-action-codes">
              {knownActionCodes.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>

            <div className="grid grid-cols-2 gap-3">
              <Select
                label="Cho phép chạy thử"
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
                  label="Cần con người xác nhận"
                  checked={form.humanRequired}
                  onChange={(v) => setField("humanRequired", v)}
                />
              </div>
            </div>

            <div className="flex min-w-0 flex-col gap-1.5">
              <span className="label-caps">Bằng chứng bắt buộc</span>
              <div className="flex flex-wrap gap-x-3 gap-y-1.5">
                {evidenceOptions.map((code) => (
                  <Checkbox
                    key={code}
                    label={evidenceLabel(code)}
                    checked={form.requiredEvidence.includes(code)}
                    onChange={() => toggleEvidence(code)}
                  />
                ))}
              </div>
              <div className="flex items-center gap-1.5">
                <input
                  value={customEvidence}
                  onChange={(e) => setCustomEvidence(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addCustomEvidence();
                    }
                  }}
                  placeholder="Bằng chứng khác…"
                  className="h-7 min-w-0 flex-1 rounded-sm border border-border bg-surface-2 px-2 text-[12.5px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-ring"
                />
                <Btn variant="outline" size="xs" onClick={addCustomEvidence}>
                  Thêm
                </Btn>
              </div>
            </div>

            <TextArea
              label="Quy trình xử lý"
              value={form.steps}
              onChange={(v) => setField("steps", v)}
              rows={3}
              placeholder={"Mỗi dòng 1 bước, theo thứ tự thực hiện"}
              hint={stepSuggestions.length > 0 ? "Bấm để thêm bước có sẵn:" : ""}
            />
            {stepSuggestions.length > 0 && (
              <div className="-mt-2 flex flex-wrap gap-1.5">
                {stepSuggestions.map((code) => (
                  <button
                    key={code}
                    type="button"
                    onClick={() => addStep(code)}
                    className="rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 text-[11px] text-muted-foreground hover:border-border-strong hover:text-foreground"
                  >
                    + {stepLabel(code)}
                  </button>
                ))}
              </div>
            )}

            {catalog && catalog.sources.length > 0 ? (
              <Panel
                title="Tài liệu tham chiếu"
                dense
                bodyClassName="max-h-52 overflow-y-auto p-3 space-y-1.5"
              >
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
                disabled={
                  createPolicy.isPending || updatePolicy.isPending || createSource.isPending
                }
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
