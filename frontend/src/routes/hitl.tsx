import { createFileRoute } from "@tanstack/react-router";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, ShieldQuestion, Timer, XCircle } from "lucide-react";
import { CameraFeed } from "@/components/qc/CameraFeed";
import { ImageLightbox } from "@/components/qc/ImageLightbox";
import { Field, Meter, Panel, VerdictBadge } from "@/components/qc/primitives";
import { cn } from "@/lib/utils";
import { useAuth, assetUrl } from "@/lib/auth";
import { useAgentRuns, useResumeInspection } from "@/lib/queries";
import type { GraphRun, ResumeAction } from "@/lib/api-types";
import { KNOWN_CAMERA_IDS, type Camera, type CameraId, type Defect } from "@/lib/qc-data";
import {
  CAMERA_POSITION_LABELS,
  SEVERITY_LABEL_VI,
  camerasFromState,
  defectsFromState,
} from "@/lib/detection-geometry";

export const Route = createFileRoute("/hitl")({
  head: () => ({
    meta: [
      { title: "Human Review Queue — AUTO QC Station 03" },
      {
        name: "description",
        content:
          "Low-confidence AI inspections queued for operator confirmation, with mandatory reason capture for every override.",
      },
      { property: "og:title", content: "Human Review Queue — AUTO QC Station 03" },
      {
        property: "og:description",
        content: "Review ambiguous AI surface-defect cases and record auditable human decisions.",
      },
    ],
  }),
  component: HitlQueue,
});

const priorities = ["All", "Critical", "High", "Medium", "Low"] as const;
type Priority = (typeof priorities)[number];

// The real QCState has no `priority` field — it's derived client-side from `severity`
// (backend severities: CRITICAL/MAJOR/MEDIUM/MINOR/UNASSESSED) purely to drive this filter.
// The legacy Lovable "Status" filter (Pending/In Review/Resolved) has no backend equivalent
// either: a case simply leaves this queue (status flips to COMPLETED) once resumed, so that
// filter is dropped rather than faked.
function derivePriority(severity: string | undefined): Exclude<Priority, "All"> {
  switch ((severity || "").toUpperCase()) {
    case "CRITICAL":
      return "Critical";
    case "MAJOR":
      return "High";
    case "MINOR":
      return "Low";
    default:
      return "Medium";
  }
}

function toPercent(value: number | undefined): number {
  if (value == null) return 0;
  return Math.round(value <= 1 ? value * 100 : value);
}

function dedupeInterrupted(runs: GraphRun[] | undefined): GraphRun[] {
  if (!runs) return [];
  // GET /agent/runs is ordered updated_at DESC (see agent/services/repository.py), so keep the
  // first (newest) run per vehicle_id — a Map built by iterating forward would instead keep the
  // oldest, which could show a case as still pending after a newer run already resolved it.
  const seen = new Set<string>();
  const latestPerVehicle: GraphRun[] = [];
  for (const run of runs) {
    if (seen.has(run.state.vehicle_id)) continue;
    seen.add(run.state.vehicle_id);
    latestPerVehicle.push(run);
  }
  // A case with human_decision already set has passed the operator's own review (it's now
  // paused at supervisor_review awaiting a supervisor's APPROVE/REJECT on the escalation, see
  // /supervisor/escalations) — an operator has nothing left to do with it here.
  return latestPerVehicle.filter(
    (run) => run.status === "INTERRUPTED" && !run.state.human_decision,
  );
}

function HitlQueue() {
  const { profile } = useAuth();
  const { data: runs, isLoading } = useAgentRuns();
  const resume = useResumeInspection();

  const [priority, setPriority] = useState<Priority>("All");
  const [openThreadId, setOpenThreadId] = useState<string | null>(null);
  const [selectedCameraId, setSelectedCameraId] = useState<CameraId | null>(null);
  const [zoomImage, setZoomImage] = useState<{
    src: string;
    alt: string;
    defects?: Defect[];
  } | null>(null);

  const [reviewer, setReviewer] = useState("");
  const [reason, setReason] = useState("");
  const [defectCode, setDefectCode] = useState("");
  const [severity, setSeverity] = useState("");
  const [disposition, setDisposition] = useState<"PASS" | "HOLD" | "REWORK" | "REINSPECT">("HOLD");
  const [location, setLocation] = useState("");
  const [lengthMm, setLengthMm] = useState("");
  const [notes, setNotes] = useState("");
  const [overrideRecommendation, setOverrideRecommendation] = useState("");
  const [validationError, setValidationError] = useState("");

  useEffect(() => {
    if (profile?.email) setReviewer((current) => current || profile.email!);
    else if (profile?.user_id) setReviewer((current) => current || profile.user_id);
  }, [profile]);

  const cases = useMemo(() => dedupeInterrupted(runs), [runs]);

  const list = useMemo(
    () => cases.filter((c) => priority === "All" || derivePriority(c.state.severity) === priority),
    [cases, priority],
  );

  const active = cases.find((c) => c.thread_id === openThreadId) ?? list[0] ?? cases[0];

  // Reset the form whenever the selected case changes so stale input from a previous
  // case can't leak into a different thread's resume payload.
  useEffect(() => {
    setSeverity(
      active?.state.severity && active.state.severity !== "UNASSESSED" ? active.state.severity : "",
    );
    setDefectCode(active?.state.classified_defect_code || "");
    setLocation(active?.state.visual_measurements?.relative_position || "");
    setLengthMm(
      active?.state.visual_measurements?.estimated_length_mm != null
        ? active.state.visual_measurements.estimated_length_mm.toFixed(1)
        : "",
    );
    setDisposition("HOLD");
    setNotes("");
    setReason("");
    setOverrideRecommendation("");
    setValidationError("");
    setSelectedCameraId(null);
  }, [active?.thread_id]);

  if (isLoading) {
    return (
      <div className="panel flex items-center justify-center px-5 py-16 font-mono text-[11px] tracking-wider text-muted-foreground">
        ĐANG TẢI HÀNG ĐỢI XÉT DUYỆT…
      </div>
    );
  }

  if (!active) {
    return (
      <div className="space-y-4">
        <header className="panel px-5 py-4">
          <h1 className="font-mono text-xl font-bold tracking-[0.18em] text-foreground">
            HÀNG ĐỢI XÉT DUYỆT (HITL)
          </h1>
          <p className="mt-1 font-mono text-[11px] tracking-wider text-muted-foreground">
            ĐỘ TIN CẬY AI DƯỚI NGƯỠNG · CẦN NHÂN VIÊN XÁC NHẬN
          </p>
        </header>
        <div className="panel px-5 py-16 text-center font-mono text-[11px] tracking-wider text-muted-foreground">
          KHÔNG CÓ CA NÀO ĐANG CHỜ DUYỆT
        </div>
      </div>
    );
  }

  const state = active.state;

  // A multi-camera submission can carry 1-5 photos and multiple findings across them
  // (agent/services/yolo_detector.py returns every detection, not just the primary one that
  // drove routing). Let the reviewer click any captured camera to feature it, instead of only
  // ever seeing the single primary detection's photo.
  const allDefects = defectsFromState(state);
  const capturedCameras = camerasFromState(state).filter((c) => c.image);
  const primaryCameraId = KNOWN_CAMERA_IDS.includes(state.camera_id as CameraId)
    ? (state.camera_id as CameraId)
    : capturedCameras[0]?.id;
  const featuredCameraId = selectedCameraId ?? primaryCameraId;
  const featuredIsPrimary = featuredCameraId === primaryCameraId;

  // overlay_image_url (agent/services/image_render.py, FR-17) only ever bakes in the single
  // PRIMARY detection's box/mask, even when its own camera has other findings too — so relying on
  // it here was silently hiding every non-primary finding on the primary camera's own photo.
  // Always use the raw photo and draw ALL of that camera's real detections client-side instead
  // (agent/graph/nodes.py's `_enrich_defects` puts every detection, primary included, into
  // `enriched_defects`/`allDefects` below) — the same client-drawn path already used for every
  // non-primary camera.
  const featuredResult = state.camera_results?.find((r) => r.camera_id === featuredCameraId);
  const featuredImage = featuredIsPrimary
    ? assetUrl(state.image_url)
    : (capturedCameras.find((c) => c.id === featuredCameraId)?.image ?? "");
  const featuredDefects = allDefects.filter((d) => d.camera === featuredCameraId);
  const featuredCamera: Camera = {
    id: featuredCameraId ?? "CAM-01",
    position: featuredCameraId ? CAMERA_POSITION_LABELS[featuredCameraId] : state.camera_id,
    image: featuredImage || "",
    captureState: featuredImage ? "CAPTURED" : "LIVE",
    health: featuredDefects.length > 0 ? "DEGRADED" : "OK",
    imageWidth: featuredResult?.image_width ?? state.image_width,
    imageHeight: featuredResult?.image_height ?? state.image_height,
  };

  async function submit(action: ResumeAction) {
    if (!active) return;
    if (reason.trim().length < 4) {
      setValidationError("CẦN NHẬP LÝ DO TRƯỚC KHI XÁC NHẬN QUYẾT ĐỊNH");
      return;
    }
    if (!reviewer.trim()) {
      setValidationError("CẦN NHẬP TÊN NGƯỜI XÉT DUYỆT");
      return;
    }
    if (action === "OVERRIDE" && overrideRecommendation.trim().length < 4) {
      setValidationError("CẦN NHẬP ĐỀ XUẤT KHI GHI ĐÈ QUYẾT ĐỊNH");
      return;
    }
    setValidationError("");
    try {
      await resume.mutateAsync({
        threadId: active.thread_id,
        payload: {
          action,
          reviewer: reviewer.trim(),
          reason: reason.trim(),
          // Mirrors the legacy frontend: a human "confirm pass" (REJECT) always forces
          // REINSPECT regardless of the disposition dropdown.
          disposition: action === "REJECT" ? "REINSPECT" : disposition,
          ...(defectCode ? { defect_code: defectCode } : {}),
          ...(severity ? { severity } : {}),
          ...(location ? { location } : {}),
          ...(lengthMm ? { length_mm: Number(lengthMm) } : {}),
          ...(notes ? { notes } : {}),
          ...(action === "OVERRIDE" ? { recommendation: overrideRecommendation.trim() } : {}),
        },
      });
      setOpenThreadId(null);
    } catch {
      // resume.error is rendered below
    }
  }

  return (
    <div className="space-y-4">
      <header className="panel flex flex-wrap items-end justify-between gap-4 px-5 py-4">
        <div>
          <h1 className="font-mono text-xl font-bold tracking-[0.18em] text-foreground">
            HÀNG ĐỢI XÉT DUYỆT (HITL)
          </h1>
          <p className="mt-1 font-mono text-[11px] tracking-wider text-muted-foreground">
            ĐỘ TIN CẬY AI DƯỚI NGƯỠNG · CẦN NHÂN VIÊN XÁC NHẬN
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-sm border border-warning/45 bg-warning/10 px-3 py-1.5 font-mono text-xs tracking-[0.14em] text-warning glow-warning">
          <Timer className="size-4" />
          {cases.length} CA ĐANG MỞ
        </div>
      </header>

      <div className="panel flex flex-wrap items-center gap-6 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="label-caps">Mức ưu tiên</span>
          {priorities.map((p) => (
            <button
              key={p}
              onClick={() => setPriority(p)}
              className={cn(
                "rounded-sm border px-2.5 py-1 font-mono text-[11px] tracking-[0.12em] transition-colors",
                priority === p
                  ? "border-warning/45 bg-warning/10 text-warning"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[400px_1fr]">
        <Panel title={`Queue (${list.length})`} bodyClassName="p-3">
          <ul className="space-y-2">
            <AnimatePresence initial={false}>
              {list.map((c) => {
                const isOpen = c.thread_id === active.thread_id;
                const cPriority = derivePriority(c.state.severity);
                return (
                  <motion.li
                    key={c.thread_id}
                    layout
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                  >
                    <button
                      onClick={() => setOpenThreadId(c.thread_id)}
                      className={cn(
                        "w-full rounded-sm border px-3 py-3 text-left transition-colors",
                        isOpen
                          ? "border-info/45 bg-info/10"
                          : "border-warning/35 bg-surface-2 hover:border-warning/60",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-sm font-semibold text-foreground">
                          {c.state.inspection_id}
                        </span>
                        <span
                          className={cn(
                            "rounded-sm border px-1.5 py-0.5 font-mono text-[10px] tracking-[0.12em]",
                            cPriority === "Critical" &&
                              "border-destructive/45 bg-destructive/10 text-destructive",
                            cPriority === "High" && "border-warning/45 bg-warning/10 text-warning",
                            (cPriority === "Medium" || cPriority === "Low") &&
                              "border-border text-muted-foreground",
                          )}
                        >
                          {cPriority.toUpperCase()}
                        </span>
                      </div>
                      <div className="label-caps mt-0.5">XE {c.state.vehicle_id}</div>
                      <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-[11px]">
                        <span className="text-foreground">{c.state.defect_type || "—"}</span>
                        <span className="text-right text-warning">
                          {toPercent(c.state.confidence)}%
                        </span>
                      </div>
                      <p className="mt-1 truncate font-mono text-[10px] tracking-wider text-muted-foreground">
                        {(c.state.reason || "").toUpperCase()}
                      </p>
                      <div className="mt-2 flex items-center justify-between">
                        <span className="font-mono text-[10px] tracking-[0.14em] text-warning">
                          ĐANG CHỜ
                        </span>
                        <VerdictBadge verdict="HITL" />
                      </div>
                    </button>
                  </motion.li>
                );
              })}
            </AnimatePresence>
            {list.length === 0 ? (
              <li className="rounded-sm border border-border px-3 py-6 text-center font-mono text-[11px] tracking-wider text-muted-foreground">
                KHÔNG CÓ CA NÀO PHÙ HỢP BỘ LỌC
              </li>
            ) : null}
          </ul>
        </Panel>

        <Panel
          title={`Ca kiểm tra ${state.inspection_id}`}
          right={
            <span className="flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] text-warning">
              <ShieldQuestion className="size-3.5" /> AI ĐỀ XUẤT: CẦN NGƯỜI XÉT DUYỆT
            </span>
          }
        >
          <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
            <CameraFeed
              camera={featuredCamera}
              defects={featuredDefects}
              className="aspect-[16/10]"
              onZoom={
                featuredCamera.image
                  ? () =>
                      setZoomImage({
                        src: featuredCamera.image,
                        alt: `${featuredCamera.id} ${featuredCamera.position} — ${state.vehicle_id}`,
                        defects: featuredDefects,
                      })
                  : undefined
              }
            />

            <div>
              <div className="rounded-sm border border-warning/45 bg-warning/10 px-4 py-4 text-center glow-warning">
                <div className="label-caps">AI đề xuất</div>
                <div className="mt-1 font-mono text-2xl font-bold tracking-[0.08em] text-warning">
                  CẦN NGƯỜI XÉT DUYỆT
                </div>
                <div className="mx-auto mt-3 max-w-[200px]">
                  <Meter value={toPercent(state.confidence)} tone="warning" />
                </div>
                <div className="mt-2 font-mono text-[11px] text-muted-foreground">
                  ĐỘ TIN CẬY AI {toPercent(state.confidence)}%
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3">
                <Field label="Loại lỗi" value={state.defect_type || "—"} />
                <Field label="Lý do AI" value={state.reason || "—"} tone="warning" />
                <Field label="Model xe" value={state.vehicle_model} />
                <Field label="Vị trí" value={state.zone_name} />
                <Field label="Mức ưu tiên" value={derivePriority(state.severity)} tone="danger" />
                <Field label="Camera" value={state.camera_id} tone="info" />
              </div>

              <div className="mt-4 space-y-3 rounded-sm border border-border bg-surface-2 p-3">
                <div className="label-caps">Thông tin quyết định QC</div>
                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    <span className="label-caps">Mã lỗi</span>
                    {state.suggested_defect_codes?.length ? (
                      <select
                        value={defectCode}
                        onChange={(e) => setDefectCode(e.target.value)}
                        className="mt-1 w-full rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground"
                      >
                        <option value="">—</option>
                        {state.suggested_defect_codes.map((d) => (
                          <option key={d.defect_code} value={d.defect_code}>
                            {d.defect_code} · {d.display_name}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        value={defectCode}
                        onChange={(e) => setDefectCode(e.target.value)}
                        placeholder="DEF-CODE"
                        className="mt-1 w-full rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground/60"
                      />
                    )}
                  </label>
                  <label className="block">
                    <span className="label-caps">Mức độ</span>
                    <select
                      value={severity}
                      onChange={(e) => setSeverity(e.target.value)}
                      className="mt-1 w-full rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground"
                    >
                      <option value="">—</option>
                      <option value="MINOR">MINOR</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="MAJOR">MAJOR</option>
                      <option value="CRITICAL">CRITICAL</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="label-caps">Xử lý</span>
                    <select
                      value={disposition}
                      onChange={(e) => setDisposition(e.target.value as typeof disposition)}
                      className="mt-1 w-full rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground"
                    >
                      <option value="PASS">PASS</option>
                      <option value="HOLD">HOLD</option>
                      <option value="REWORK">REWORK</option>
                      <option value="REINSPECT">REINSPECT</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="label-caps">Chiều dài (mm)</span>
                    <input
                      value={lengthMm}
                      onChange={(e) => setLengthMm(e.target.value)}
                      inputMode="decimal"
                      placeholder="—"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground/60"
                    />
                  </label>
                  <label className="col-span-2 block">
                    <span className="label-caps">Vị trí</span>
                    <input
                      value={location}
                      onChange={(e) => setLocation(e.target.value)}
                      placeholder="vd. cửa trái"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground/60"
                    />
                  </label>
                  <label className="col-span-2 block">
                    <span className="label-caps">Người xét duyệt</span>
                    <input
                      value={reviewer}
                      onChange={(e) => setReviewer(e.target.value)}
                      placeholder="Tên hoặc email người xét duyệt"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground/60"
                    />
                  </label>
                </div>
              </div>

              <div className="mt-4">
                <label className="label-caps" htmlFor="reason">
                  Lý do (bắt buộc khi override AI)
                </label>
                <textarea
                  id="reason"
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Vết xước lộ rõ dưới ánh sáng kiểm tra."
                  className={cn(
                    "mt-1 w-full resize-none rounded-sm border bg-surface-2 px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-info/50",
                    validationError ? "border-destructive/60" : "border-border",
                  )}
                />

                <label className="label-caps mt-2 block" htmlFor="notes">
                  Ghi chú (tùy chọn)
                </label>
                <textarea
                  id="notes"
                  rows={1}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="mt-1 w-full resize-none rounded-sm border border-border bg-surface-2 px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-info/50"
                />

                <label className="label-caps mt-2 block" htmlFor="override-recommendation">
                  Đề xuất chuyển cấp (bắt buộc khi chọn REVIEW / ESCALATE)
                </label>
                <input
                  id="override-recommendation"
                  value={overrideRecommendation}
                  onChange={(e) => setOverrideRecommendation(e.target.value)}
                  placeholder="Chuyển cho giám sát để ghi đè chính sách…"
                  className="mt-1 w-full rounded-sm border border-border bg-surface-2 px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-info/50"
                />

                {validationError ? (
                  <p className="mt-1 font-mono text-[11px] text-destructive">{validationError}</p>
                ) : null}
                {resume.isError ? (
                  <p className="mt-1 font-mono text-[11px] text-destructive">
                    {resume.error instanceof Error
                      ? resume.error.message
                      : "Gửi quyết định thất bại."}
                  </p>
                ) : null}

                <div className="mt-3 grid grid-cols-3 gap-2">
                  <button
                    disabled={resume.isPending}
                    onClick={() => void submit("APPROVE")}
                    className="flex flex-col items-center gap-1 rounded-sm border border-destructive/45 bg-destructive/10 px-3 py-3 font-mono text-[11px] tracking-[0.12em] text-destructive transition-colors hover:bg-destructive/20 disabled:opacity-50"
                  >
                    <XCircle className="size-5" /> XÁC NHẬN FAIL
                  </button>
                  <button
                    disabled={resume.isPending}
                    onClick={() => void submit("REJECT")}
                    className="flex flex-col items-center gap-1 rounded-sm border border-success/45 bg-success/10 px-3 py-3 font-mono text-[11px] tracking-[0.12em] text-success transition-colors hover:bg-success/20 disabled:opacity-50"
                  >
                    <CheckCircle2 className="size-5" /> XÁC NHẬN PASS
                  </button>
                  <button
                    disabled={resume.isPending}
                    onClick={() => void submit("OVERRIDE")}
                    className="flex flex-col items-center gap-1 rounded-sm border border-info/45 bg-info/10 px-3 py-3 font-mono text-[11px] tracking-[0.12em] text-info transition-colors hover:bg-info/20 disabled:opacity-50"
                  >
                    <ShieldQuestion className="size-5" /> CHUYỂN CẤP XÉT DUYỆT
                  </button>
                </div>
              </div>
            </div>
          </div>

          {capturedCameras.length > 1 || allDefects.length > 1 ? (
            <div className="mt-4 border-t border-border pt-4">
              <div className="label-caps mb-2">
                Toàn bộ camera đã chụp ({capturedCameras.length}) · {allDefects.length} lỗi phát
                hiện · nhấn vào 1 camera để xem lớn
              </div>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
                {capturedCameras.map((cam) => {
                  const camDefects = allDefects.filter((d) => d.camera === cam.id);
                  return (
                    <CameraFeed
                      key={cam.id}
                      camera={cam}
                      defects={camDefects}
                      className="aspect-[16/10]"
                      selected={cam.id === featuredCameraId}
                      onSelectCamera={() => setSelectedCameraId(cam.id)}
                      onZoom={() =>
                        setZoomImage({
                          src: cam.image,
                          alt: `${cam.id} ${cam.position}`,
                          defects: camDefects,
                        })
                      }
                    />
                  );
                })}
              </div>
              <ul className="mt-3 grid gap-2 md:grid-cols-2">
                {allDefects.map((d) => (
                  <li
                    key={d.id}
                    className="flex items-center justify-between gap-3 rounded-sm border border-border bg-surface-2 px-3 py-2"
                  >
                    <span className="min-w-0">
                      <span className="block font-mono text-xs text-foreground">
                        #{String(d.index).padStart(2, "0")} {d.type} — {d.location}
                      </span>
                      <span className="label-caps block">
                        {d.camera} · {d.measurement} · {SEVERITY_LABEL_VI[d.severity]}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                      {d.confidence}%
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </Panel>
      </div>

      {zoomImage ? (
        <ImageLightbox
          src={zoomImage.src}
          alt={zoomImage.alt}
          defects={zoomImage.defects}
          onClose={() => setZoomImage(null)}
        />
      ) : null}
    </div>
  );
}
