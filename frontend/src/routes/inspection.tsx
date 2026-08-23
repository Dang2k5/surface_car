import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { Cpu, Images, Loader2, Ruler, ScanSearch, ShieldCheck, UploadCloud } from "lucide-react";
import { KNOWN_CAMERA_IDS, type CameraId, type Defect } from "@/lib/qc-data";
import { CameraFeed } from "@/components/qc/CameraFeed";
import { ImageLightbox } from "@/components/qc/ImageLightbox";
import { Field, Meter, Panel, VerdictBadge } from "@/components/qc/primitives";
import { cn } from "@/lib/utils";
import { assetUrl } from "@/lib/auth";
import {
  useAgentRuns,
  useAllocateLotProduct,
  useCreateLot,
  useLots,
  useShifts,
  useStations,
  useSubmitInspection,
} from "@/lib/queries";
import type { GraphRun } from "@/lib/api-types";
import {
  SEVERITY_LABEL_VI,
  camerasFromState,
  defectsFromState,
  mapSeverity,
} from "@/lib/detection-geometry";

export const Route = createFileRoute("/inspection")({
  head: () => ({
    meta: [
      { title: "Vehicle Inspection — AUTO QC Station 03" },
      {
        name: "description",
        content:
          "Five-camera surface inspection command center with AI defect detection overlays, agent verdict and defect evidence.",
      },
      { property: "og:title", content: "Vehicle Inspection — AUTO QC Station 03" },
      {
        property: "og:description",
        content:
          "Five-camera AI surface inspection with defect overlays and auditable agent verdict.",
      },
    ],
  }),
  component: InspectionPage,
});

type CameraFormRow = { cameraId: CameraId; file: File | null };

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

function UploadPanel({ onSubmitted }: { onSubmitted: (run: GraphRun) => void }) {
  const submit = useSubmitInspection();
  const shiftsQuery = useShifts();
  const lotsQuery = useLots();
  const stationsQuery = useStations();
  const createLot = useCreateLot();
  const allocateProduct = useAllocateLotProduct();
  const [vehicleModel, setVehicleModel] = useState("");
  const [stationId, setStationId] = useState("");
  const [lotId, setLotId] = useState("");
  const [shiftId, setShiftId] = useState("");
  const [productionDate, setProductionDate] = useState(todayIsoDate());
  const [rows, setRows] = useState<CameraFormRow[]>([{ cameraId: "CAM-01", file: null }]);
  const [creatingLot, setCreatingLot] = useState(false);
  const [newLotId, setNewLotId] = useState("");
  const [newLotName, setNewLotName] = useState("");
  const [newProductModel, setNewProductModel] = useState("");
  const [newQuantity, setNewQuantity] = useState("");
  const [newLotError, setNewLotError] = useState("");
  const [submitError, setSubmitError] = useState("");

  const shifts = shiftsQuery.data ?? [];
  const lots = lotsQuery.data ?? [];
  const stations = stationsQuery.data ?? [];

  useEffect(() => {
    if (!stationId && stations.length > 0) setStationId(stations[0]!.station_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stationId, stations.length]);

  // Selecting a lot is what determines its Trạm+Ca (handleLotChange below), not the other way
  // around — there's no station picker in this form, and Ca starts unselected, so filtering the
  // list by the current station/shift would hide every lot until the user already knew its exact
  // shift beforehand. Show every active lot instead.
  const availableLots = lots;

  function handleLotChange(nextLotId: string) {
    setLotId(nextLotId);
    const lot = lots.find((l) => l.lot_id === nextLotId);
    if (lot?.station_id) setStationId(lot.station_id);
    if (lot?.shift_id) setShiftId(lot.shift_id);
    setVehicleModel(lot?.product_model ?? "");
  }

  async function handleCreateLot() {
    setNewLotError("");
    const quantityNum = Number(newQuantity);
    if (!newLotId.trim() || !newLotName.trim()) {
      setNewLotError("Cần nhập mã lô và tên lô.");
      return;
    }
    if (!stationId || !shiftId) {
      setNewLotError("Chọn Trạm và Ca trước khi tạo lô mới.");
      return;
    }
    if (!newProductModel.trim()) {
      setNewLotError("Cần nhập Model sản phẩm.");
      return;
    }
    if (!newQuantity || !Number.isInteger(quantityNum) || quantityNum < 1) {
      setNewLotError("Cần nhập Số lượng (số nguyên >= 1).");
      return;
    }
    try {
      const lot = await createLot.mutateAsync({
        lot_id: newLotId.trim(),
        name: newLotName.trim(),
        station_id: stationId,
        shift_id: shiftId,
        product_model: newProductModel.trim(),
        quantity: quantityNum,
      });
      setLotId(lot.lot_id);
      setVehicleModel(lot.product_model);
      setNewLotId("");
      setNewLotName("");
      setNewProductModel("");
      setNewQuantity("");
      setCreatingLot(false);
    } catch (err) {
      setNewLotError(err instanceof Error ? err.message : "Tạo lô thất bại.");
    }
  }

  const addRow = () => {
    const used = new Set(rows.map((r) => r.cameraId));
    const next = KNOWN_CAMERA_IDS.find((id) => !used.has(id));
    if (next) setRows((r) => [...r, { cameraId: next, file: null }]);
  };

  const missing: string[] = [];
  if (!lotId) missing.push("Lô sản xuất");
  if (!shiftId) missing.push("Ca làm việc");
  if (lotId && !vehicleModel)
    missing.push("Model sản phẩm (lô chưa có model, cập nhật ở Quản lý Lô)");
  if (!rows.every((r) => r.file)) missing.push("Ảnh cho mỗi camera đã thêm");

  const canSubmit = missing.length === 0;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitError("");
    let resolvedVehicleId: string;
    // Mã sản phẩm sinh tự động khi xe đi qua camera: <Mã Lô>-<Model sản phẩm>-<STT>.
    try {
      const product = await allocateProduct.mutateAsync({
        lotId,
        payload: { vehicle_model: vehicleModel },
      });
      resolvedVehicleId = product.product_code;
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Sinh mã sản phẩm thất bại.");
      return;
    }
    const filled = rows.filter((r): r is { cameraId: CameraId; file: File } => !!r.file);
    const shiftLotFields = {
      ...(lotId.trim() ? { lotId: lotId.trim() } : {}),
      ...(shiftId ? { shiftId } : {}),
      ...(productionDate ? { productionDate } : {}),
      ...(stationId ? { stationId } : {}),
    };
    const payload =
      filled.length > 1
        ? {
            cameras: filled.map((r) => ({ file: r.file, cameraId: r.cameraId })),
            vehicleId: resolvedVehicleId,
            vehicleModel,
            ...shiftLotFields,
          }
        : {
            file: filled[0]!.file,
            cameraId: filled[0]!.cameraId,
            vehicleId: resolvedVehicleId,
            vehicleModel,
            ...shiftLotFields,
          };
    const run = await submit.mutateAsync(payload);
    onSubmitted(run);
  }

  return (
    <Panel title="Gửi yêu cầu kiểm tra" right={<span className="label-caps">1–5 camera</span>}>
      <div className="grid gap-3 md:grid-cols-2">
        <input
          value={vehicleModel}
          readOnly
          placeholder="Model sản phẩm"
          className="rounded-sm border border-border bg-surface-2 px-2 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground"
        />
        {creatingLot ? (
          <div className="space-y-1.5 md:col-span-2">
            <div className="flex flex-wrap gap-2">
              <input
                value={newLotId}
                onChange={(e) => setNewLotId(e.target.value)}
                placeholder="Mã lô mới (VD: LOT-2026-08-22-A)"
                autoFocus
                className="flex-1 rounded-sm border border-info/40 bg-background px-2 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground"
              />
              <input
                value={newLotName}
                onChange={(e) => setNewLotName(e.target.value)}
                placeholder="Tên lô"
                className="w-40 rounded-sm border border-info/40 bg-background px-2 py-1.5 text-xs text-foreground placeholder:text-muted-foreground"
              />
              <input
                value={newProductModel}
                onChange={(e) => setNewProductModel(e.target.value)}
                placeholder="Model sản phẩm (VD: VF8)"
                className="w-36 rounded-sm border border-info/40 bg-background px-2 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground"
              />
              <input
                type="number"
                min={1}
                value={newQuantity}
                onChange={(e) => setNewQuantity(e.target.value)}
                placeholder="Số lượng"
                className="w-24 rounded-sm border border-info/40 bg-background px-2 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground"
              />
              <button
                type="button"
                onClick={() => void handleCreateLot()}
                disabled={createLot.isPending}
                className="rounded-sm border border-info/40 bg-info/10 px-3 py-1.5 font-mono text-[11px] tracking-[0.1em] text-info disabled:opacity-60"
              >
                {createLot.isPending ? "Đang tạo…" : "Tạo lô"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setCreatingLot(false);
                  setNewLotId("");
                  setNewLotName("");
                  setNewProductModel("");
                  setNewQuantity("");
                  setNewLotError("");
                }}
                className="rounded-sm border border-border px-3 py-1.5 font-mono text-[11px] tracking-[0.1em] text-muted-foreground"
              >
                Hủy
              </button>
            </div>
            {newLotError ? <p className="text-[11px] text-destructive">{newLotError}</p> : null}
          </div>
        ) : (
          <select
            value={lotId}
            onChange={(e) => {
              if (e.target.value === "__new__") {
                setCreatingLot(true);
                return;
              }
              handleLotChange(e.target.value);
            }}
            className="rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground"
          >
            <option value="">Chọn lô sản xuất</option>
            {availableLots.map((l) => (
              <option key={l.lot_id} value={l.lot_id}>
                {l.lot_id} — {l.name}
              </option>
            ))}
            <option value="__new__">+ Tạo lô mới…</option>
          </select>
        )}
        <select
          value={shiftId}
          onChange={(e) => setShiftId(e.target.value)}
          className="rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground"
        >
          <option value="">Chọn ca</option>
          {shifts.map((s) => (
            <option key={s.shift_id} value={s.shift_id}>
              {s.name}
            </option>
          ))}
        </select>
        <input
          type="date"
          value={productionDate}
          onChange={(e) => setProductionDate(e.target.value)}
          className="rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground"
        />
      </div>

      <div className="mt-3 space-y-2">
        {rows.map((row, i) => (
          <div key={i} className="flex items-center gap-2">
            <select
              value={row.cameraId}
              onChange={(e) =>
                setRows((r) =>
                  r.map((x, idx) =>
                    idx === i ? { ...x, cameraId: e.target.value as CameraId } : x,
                  ),
                )
              }
              className="rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground"
            >
              {KNOWN_CAMERA_IDS.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
            <input
              type="file"
              accept="image/jpeg,image/png"
              onChange={(e) =>
                setRows((r) =>
                  r.map((x, idx) => (idx === i ? { ...x, file: e.target.files?.[0] ?? null } : x)),
                )
              }
              className="flex-1 font-mono text-xs text-muted-foreground"
            />
          </div>
        ))}
        {rows.length < 5 ? (
          <button
            onClick={addRow}
            className="font-mono text-[11px] tracking-[0.1em] text-info hover:underline"
          >
            + THÊM CAMERA
          </button>
        ) : null}
      </div>

      <button
        onClick={handleSubmit}
        disabled={!canSubmit || submit.isPending || allocateProduct.isPending}
        className={cn(
          "mt-4 flex w-full items-center justify-center gap-2 rounded-sm border px-3 py-2 font-mono text-[11px] tracking-[0.14em]",
          canSubmit && !submit.isPending && !allocateProduct.isPending
            ? "border-info/45 bg-info/10 text-info"
            : "border-border text-muted-foreground opacity-60",
        )}
      >
        {submit.isPending || allocateProduct.isPending ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <UploadCloud className="size-3.5" />
        )}
        GỬI KIỂM TRA
      </button>
      {!canSubmit ? (
        <p className="mt-2 text-[11px] text-muted-foreground">Còn thiếu: {missing.join(", ")}</p>
      ) : null}
      {submitError ? <p className="mt-2 text-[11px] text-destructive">{submitError}</p> : null}
      {submit.isError ? (
        <p className="mt-2 text-[11px] text-destructive">
          {submit.error instanceof Error ? submit.error.message : "Gửi yêu cầu thất bại."}
        </p>
      ) : null}
    </Panel>
  );
}

function InspectionPage() {
  const { data: runs } = useAgentRuns();
  const [submittedRun, setSubmittedRun] = useState<GraphRun | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [zoomImage, setZoomImage] = useState<{
    src: string;
    alt: string;
    defects?: Defect[];
  } | null>(null);

  // Backend has no "current run" concept; use the most recently submitted run this session,
  // falling back to the first entry in the polled runs list (GET /agent/runs is ordered by
  // updated_at DESC, so index 0 is the most recent — see agent/services/repository.py).
  const activeRun = submittedRun ?? (runs && runs.length > 0 ? runs[0] : undefined);
  const state = activeRun?.state;

  const defects = useMemo(() => defectsFromState(state), [state]);
  const camerasForRun = useMemo(() => camerasFromState(state), [state]);
  const defect = defects.find((d) => d.id === selected) ?? defects[0];

  const cam = (id: CameraId) => camerasForRun.find((c) => c.id === id)!;
  const defectsFor = (id: CameraId) => defects.filter((d) => d.camera === id);

  // final_status (agent/graph/nodes.py, agent/services/policy.py) is exactly PASS or FAIL once
  // the graph completes; while a run is paused for HITL it has no final_status yet.
  const verdict = activeRun?.status === "INTERRUPTED" ? "CẦN NGƯỜI KIỂM" : state?.final_status;

  // Every detection now gets its own rendered crop (agent/services/image_render.py, FR-17,
  // backend/app/langgraph_api.py's _attach_rendered_defect_images), not just the primary one.
  // Fall back to that detection's full camera photo only when its own crop hasn't rendered
  // (e.g. render failed for that detection), same as the "ẢNH GỐC" button below.
  const defectCropImage = defect ? defect.cropImageUrl || cam(defect.camera).image : "";

  if (!activeRun || !state) {
    return (
      <div className="space-y-4">
        <UploadPanel onSubmitted={setSubmittedRun} />
        <Panel title="Kiểm tra xe">
          <p className="text-sm text-muted-foreground">
            Chưa có lần kiểm tra nào. Gửi ảnh camera phía trên để bắt đầu kiểm tra bề mặt bằng AI.
          </p>
        </Panel>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <header className="panel flex flex-wrap items-center gap-6 px-5 py-4">
        <div>
          <h1 className="font-mono text-xl font-bold tracking-[0.18em] text-foreground">
            KIỂM TRA XE
          </h1>
          <p className="mt-1 font-mono text-[11px] tracking-wider text-muted-foreground">
            {state.vehicle_model} | VIN: {state.vehicle_id} | Inspection #{state.inspection_id}
          </p>
        </div>
        <div className="ml-auto grid grid-cols-2 gap-x-8 gap-y-2 md:grid-cols-3">
          <Field label="Model" value={state.vehicle_model} />
          <Field label="Trạm" value={state.station_id || "—"} />
          <Field
            label="Trạng thái"
            value={activeRun.status === "INTERRUPTED" ? "Chờ QC duyệt" : "Hoàn tất"}
            tone={activeRun.status === "INTERRUPTED" ? "warning" : "info"}
          />
        </div>
      </header>

      <UploadPanel onSubmitted={setSubmittedRun} />

      {activeRun.status === "INTERRUPTED" ? (
        <div className="panel flex items-center justify-between gap-3 border-warning/45 bg-warning/10 px-4 py-3">
          <span className="text-sm text-foreground">
            {state.reason ||
              "Lần kiểm tra này cần nhân viên QC xét duyệt trước khi có kết luận cuối."}
          </span>
          <Link
            to="/hitl"
            className="shrink-0 rounded-sm border border-warning/45 bg-warning/15 px-3 py-1.5 font-mono text-[11px] tracking-[0.12em] text-warning"
          >
            XÉT DUYỆT TRONG HÀNG ĐỢI HITL
          </Link>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1.75fr_1fr]">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            {KNOWN_CAMERA_IDS.slice(0, 4).map((id) => (
              <CameraFeed
                key={id}
                camera={cam(id)}
                defects={defectsFor(id)}
                selectedDefect={selected}
                onSelectDefect={setSelected}
                onZoom={() =>
                  setZoomImage({
                    src: cam(id).image,
                    alt: `${id} ${cam(id).position}`,
                    defects: defectsFor(id),
                  })
                }
                className="aspect-[16/10]"
              />
            ))}
            <CameraFeed
              camera={cam("CAM-05")}
              defects={defectsFor("CAM-05")}
              selectedDefect={selected}
              onSelectDefect={setSelected}
              onZoom={() =>
                setZoomImage({
                  src: cam("CAM-05").image,
                  alt: `CAM-05 ${cam("CAM-05").position}`,
                  defects: defectsFor("CAM-05"),
                })
              }
              className="col-span-2 aspect-[32/10]"
            />
          </div>

          <Panel
            title="Chi tiết lỗi"
            right={
              <span className="label-caps">
                {defects.length} phát hiện · nhấn vào khung để chọn
              </span>
            }
          >
            {defect ? (
              <div className="grid gap-4 md:grid-cols-[260px_1fr]">
                <div className="relative overflow-hidden rounded-sm border border-destructive/40">
                  <img
                    src={defectCropImage}
                    alt={`Ảnh cắt ${defect.type} tại ${defect.location}`}
                    loading="lazy"
                    width={1024}
                    height={640}
                    className="h-40 w-full cursor-zoom-in object-cover"
                    onClick={() =>
                      setZoomImage({
                        src: defectCropImage,
                        alt: `Ảnh cắt ${defect.type} tại ${defect.location}`,
                      })
                    }
                  />
                  <div className="scan-lines pointer-events-none absolute inset-0" />
                  <span className="absolute left-2 top-2 rounded-sm bg-destructive/85 px-1.5 font-mono text-[10px] font-semibold text-background">
                    ẢNH CẮT LỖI · {defect.camera}
                  </span>
                </div>

                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <h3 className="font-mono text-lg font-bold text-foreground">
                      LỖI #{String(defect.index).padStart(2, "0")}
                    </h3>
                    <VerdictBadge verdict={defect.decision} />
                    <span className="rounded-sm border border-border bg-surface-2 px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                      {SEVERITY_LABEL_VI[defect.severity].toUpperCase()}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-4">
                    <Field label="Loại lỗi" value={defect.type} />
                    <Field label="Vị trí" value={defect.location} />
                    <Field label="Độ tin cậy" value={`${defect.confidence}%`} tone="info" />
                    <Field label="Camera" value={defect.camera} />
                    <Field label="Kích thước" value={defect.measurement} tone="danger" />
                    <Field label="Ngưỡng" value={defect.threshold} />
                    <Field
                      label="Khung bao"
                      value={`x${defect.box.x.toFixed(0)} y${defect.box.y.toFixed(0)} w${defect.box.w.toFixed(0)} h${defect.box.h.toFixed(0)}`}
                    />
                    <Field
                      label="Kết luận"
                      value={defect.decision}
                      tone={defect.decision === "FAIL" ? "danger" : "success"}
                    />
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      onClick={() =>
                        setZoomImage({
                          src: defectCropImage,
                          alt: `Ảnh cắt ${defect.type} tại ${defect.location}`,
                        })
                      }
                      className="inline-flex items-center gap-1.5 rounded-sm border border-border px-2.5 py-1.5 font-mono text-[11px] tracking-[0.12em] text-muted-foreground transition-colors hover:border-info/45 hover:text-info"
                    >
                      <ScanSearch className="size-3.5" /> PHÓNG TO
                    </button>
                    <button
                      onClick={() =>
                        setZoomImage({
                          src: cam(defect.camera).image,
                          alt: `Ảnh gốc ${defect.camera}`,
                          // Only the full (uncropped) camera photo has a coordinate frame the
                          // box/mask % positions can reliably map onto — crop_image_url above is
                          // an already-padded crop with no known offset, so it stays unmarked.
                          defects: defectsFor(defect.camera),
                        })
                      }
                      className="inline-flex items-center gap-1.5 rounded-sm border border-border px-2.5 py-1.5 font-mono text-[11px] tracking-[0.12em] text-muted-foreground transition-colors hover:border-info/45 hover:text-info"
                    >
                      <Images className="size-3.5" /> ẢNH GỐC
                    </button>
                    {[
                      { label: "ẢNH CẮT LỖI", icon: Ruler },
                      { label: "SO SÁNH THAM CHIẾU", icon: ShieldCheck },
                    ].map(({ label, icon: Icon }) => (
                      <button
                        key={label}
                        disabled
                        title="Chưa nối với backend"
                        className="inline-flex items-center gap-1.5 rounded-sm border border-border px-2.5 py-1.5 font-mono text-[11px] tracking-[0.12em] text-muted-foreground opacity-60"
                      >
                        <Icon className="size-3.5" /> {label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Không phát hiện lỗi nào trong lần kiểm tra này.
              </p>
            )}
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel
            title="Kết luận của AI Agent"
            right={
              <span className="flex items-center gap-1.5 font-mono text-[11px] text-info">
                <Cpu className="size-3.5" /> {state.classified_defect_code || "—"}
              </span>
            }
          >
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={cn(
                "rounded-sm border px-4 py-5 text-center",
                verdict === "PASS"
                  ? "border-success/45 bg-success/10 glow-success"
                  : verdict === "CẦN NGƯỜI KIỂM"
                    ? "border-warning/45 bg-warning/10 glow-warning"
                    : "border-destructive/45 bg-destructive/10 glow-danger",
              )}
            >
              <div className="label-caps">Kết luận</div>
              <div
                className={cn(
                  "mt-1 font-mono text-5xl font-bold tracking-[0.1em]",
                  verdict === "PASS"
                    ? "text-success"
                    : verdict === "CẦN NGƯỜI KIỂM"
                      ? "text-warning"
                      : "text-destructive",
                )}
              >
                {verdict}
              </div>
              <div className="mt-3 font-mono text-[11px] tracking-wider text-muted-foreground">
                ĐỘ TIN CẬY AGENT{" "}
                {state.confidence != null ? Math.round(state.confidence * 1000) / 10 : "—"}%
              </div>
              <div className="mx-auto mt-3 max-w-[220px]">
                <Meter
                  value={state.confidence != null ? state.confidence * 100 : 0}
                  tone="danger"
                />
              </div>
            </motion.div>

            <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3">
              <Field label="Số lỗi phát hiện" value={defects.length} tone="danger" />
              <Field
                label="Mức độ"
                value={state.severity ? SEVERITY_LABEL_VI[mapSeverity(state.severity)] : "—"}
                tone="warning"
              />
            </div>

            <div className="mt-4 rounded-sm border border-border bg-surface-2 p-3">
              <div className="label-caps">Tóm tắt lý do</div>
              <p className="mt-1 text-sm leading-snug text-foreground">
                {state.reason ||
                  state.recommendation ||
                  "Không có tóm tắt lý do cho lần kiểm tra này."}
              </p>
            </div>

            <div className="mt-4 space-y-2">
              {defects.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelected(d.id)}
                  className={cn(
                    "flex w-full items-center justify-between gap-3 rounded-sm border px-3 py-2 text-left transition-colors",
                    selected === d.id
                      ? "border-info/45 bg-info/10"
                      : "border-border bg-surface-2 hover:border-border-strong",
                  )}
                >
                  <span className="min-w-0">
                    <span className="block font-mono text-xs text-foreground">
                      #{String(d.index).padStart(2, "0")} {d.type} — {d.location}
                    </span>
                    <span className="label-caps block">
                      {d.camera} · {d.measurement} · {SEVERITY_LABEL_VI[d.severity]}
                    </span>
                  </span>
                  <VerdictBadge verdict={d.decision} />
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="Nhật ký kiểm tra">
            {state.execution_trace?.length ? (
              <ol className="space-y-3">
                {state.execution_trace.map((a, i) => (
                  <li key={`${a.node}-${i}`} className="flex gap-3">
                    <span className="font-mono text-[11px] text-info">{a.status}</span>
                    <span className="min-w-0">
                      <span className="label-caps block">{a.node}</span>
                      <span className="block text-sm leading-snug text-foreground">{a.detail}</span>
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted-foreground">
                Chưa có nhật ký thực thi cho lần kiểm tra này.
              </p>
            )}
          </Panel>
        </div>
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
