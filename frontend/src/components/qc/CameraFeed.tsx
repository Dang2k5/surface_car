import { useState } from "react";
import { motion } from "motion/react";
import { Maximize2, VideoOff } from "lucide-react";
import type { Camera, Defect } from "@/lib/qc-data";
import { cn } from "@/lib/utils";
import { Dot } from "./primitives";

// Matches the video-upload endpoint's default frame_interval (backend/app/langgraph_api.py) —
// a tracked defect's box shows while the video is within one extraction interval of a moment
// it was actually observed in, instead of only at the exact frame timestamp.
const TRACK_WINDOW_SECONDS = 0.75;

function isDefectVisibleAt(defect: Defect, videoTime: number | null): boolean {
  if (videoTime === null || !defect.trackTimestamps?.length) return true;
  return defect.trackTimestamps.some((t) => Math.abs(t - videoTime) <= TRACK_WINDOW_SECONDS);
}

export function DefectOverlay({
  defect,
  active,
  onSelect,
}: {
  defect: Defect;
  active: boolean;
  onSelect: () => void;
}) {
  const hasMask = !!defect.polygon && defect.polygon.length >= 3;
  const tone = defect.decision === "FAIL" ? "border-destructive" : "border-warning";
  const label = defect.decision === "FAIL" ? "bg-destructive/85" : "bg-warning/85";
  return (
    <motion.button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.35 }}
      className={cn(
        "absolute text-left",
        // A segmentation mask polygon is drawn separately (see CameraFeed's <svg>); this box then
        // only needs to be a click target + label anchor, not a duplicate rectangle outline.
        hasMask ? "border border-transparent" : cn("border-2", tone),
        active && "ring-2 ring-info ring-offset-1 ring-offset-background",
      )}
      style={{
        left: `${defect.box.x}%`,
        top: `${defect.box.y}%`,
        width: `${defect.box.w}%`,
        height: `${defect.box.h}%`,
      }}
    >
      <span
        className={cn(
          "absolute -top-5 left-0 whitespace-nowrap px-1.5 font-mono text-[10px] font-semibold tracking-wider text-background",
          label,
        )}
      >
        {defect.type.toUpperCase()} #{String(defect.index).padStart(2, "0")} · {defect.confidence}%
      </span>
    </motion.button>
  );
}

export function CameraFeed({
  camera,
  defects,
  className,
  selectedDefect,
  onSelectDefect,
  onZoom,
  onSelectCamera,
  selected,
}: {
  camera: Camera;
  defects: Defect[];
  className?: string;
  selectedDefect?: string | null;
  onSelectDefect?: (id: string) => void;
  /** Renders the zoom button and opens a full-screen lightbox for this camera's image. */
  onZoom?: (() => void) | undefined;
  /** Makes the whole card clickable (e.g. HITL's camera picker) without affecting defect clicks. */
  onSelectCamera?: () => void;
  selected?: boolean;
}) {
  // Only meaningful while an actual <video> plays back (null for a static-photo camera, where
  // every defect stays visible) -- tracks the player's currentTime so defects with
  // trackTimestamps can fade in/out at the moments they were actually observed.
  const [videoTime, setVideoTime] = useState<number | null>(camera.videoUrl ? 0 : null);
  const visibleDefects = defects.filter((d) => isDefectVisibleAt(d, videoTime));
  const withMask = visibleDefects.filter((d) => d.polygon && d.polygon.length >= 3);
  // The image renders with object-contain, so it's letterboxed to the real photo's own aspect
  // ratio inside this fixed aspect-[16/10] card. A viewBox of "0 0 100 100" with
  // preserveAspectRatio="none" (stretch) assumed the photo filled the card edge-to-edge, which
  // silently shifted the mask off the real defect on any camera whose native aspect ratio wasn't
  // 16:10. Using the camera's own pixel dimensions as the viewBox with the SVG's default
  // "meet" scaling reproduces the exact same letterbox math the <img> already uses, so the mask
  // lines up regardless of that camera's resolution/aspect ratio.
  const imgW = camera.imageWidth ?? 100;
  const imgH = camera.imageHeight ?? 100;

  return (
    <div
      role={onSelectCamera ? "button" : undefined}
      tabIndex={onSelectCamera ? 0 : undefined}
      onClick={onSelectCamera}
      className={cn(
        "group relative overflow-hidden rounded-sm border bg-background",
        camera.health === "DEGRADED" ? "border-warning/50" : "border-border",
        onSelectCamera && "cursor-pointer",
        selected && "ring-2 ring-info ring-offset-1 ring-offset-background",
        className,
      )}
    >
      {camera.image ? (
        // The SVG mask below already accounts for letterboxing (its viewBox is the photo's own
        // pixel size, so its "meet" scaling matches object-contain). DefectOverlay's box, though,
        // is plain % positioning — it needs its containing block to BE the letterboxed image area,
        // not the fixed aspect-[16/10] card, or its box drifts off the real defect whenever a
        // camera's native aspect ratio differs from the card's. Sizing this wrapper to the photo's
        // own aspect ratio (absolute + inset-0 + m-auto + max-h/w-full centers and contain-fits it,
        // same result object-contain gives the <img>) makes every % overlay inside it line up.
        <div
          className="absolute inset-0 m-auto max-h-full max-w-full"
          style={{ aspectRatio: `${imgW} / ${imgH}` }}
        >
          {camera.videoUrl ? (
            <video
              src={camera.videoUrl}
              poster={camera.image}
              controls
              muted
              playsInline
              onClick={(e) => e.stopPropagation()}
              onTimeUpdate={(e) => setVideoTime(e.currentTarget.currentTime)}
              onSeeked={(e) => setVideoTime(e.currentTarget.currentTime)}
              className="h-full w-full object-contain opacity-90"
            />
          ) : (
            <img
              src={camera.image}
              alt={`${camera.id} ${camera.position} capture`}
              loading="lazy"
              width={1024}
              height={640}
              className="h-full w-full object-contain opacity-90"
            />
          )}

          {withMask.length > 0 ? (
            <svg
              className="pointer-events-none absolute inset-0 h-full w-full"
              viewBox={`0 0 ${imgW} ${imgH}`}
            >
              {withMask.map((d) => (
                <polygon
                  key={d.id}
                  points={d
                    .polygon!.map((p) => `${(p.x / 100) * imgW},${(p.y / 100) * imgH}`)
                    .join(" ")}
                  vectorEffect="non-scaling-stroke"
                  className={cn(
                    d.decision === "FAIL"
                      ? "fill-destructive/25 stroke-destructive"
                      : "fill-warning/25 stroke-warning",
                    selectedDefect === d.id ? "stroke-[2.5]" : "stroke-[1.5]",
                  )}
                />
              ))}
            </svg>
          ) : null}

          {visibleDefects.map((d) => (
            <DefectOverlay
              key={d.id}
              defect={d}
              active={selectedDefect === d.id}
              onSelect={() => onSelectDefect?.(d.id)}
            />
          ))}
        </div>
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-surface-2 text-muted-foreground">
          <VideoOff className="size-6" />
          <span className="font-mono text-[11px] tracking-[0.12em]">CHƯA CÓ ẢNH</span>
        </div>
      )}
      <div className="scan-lines pointer-events-none absolute inset-0" />

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between gap-2 bg-gradient-to-b from-background/90 to-transparent px-2.5 py-2">
        <span className="flex items-center gap-2 font-mono text-[11px] font-semibold tracking-wider text-foreground">
          {camera.id}
          <span className="text-muted-foreground">{camera.position}</span>
        </span>
        <span
          className={cn(
            "flex items-center gap-1.5 rounded-sm border px-1.5 py-0.5 font-mono text-[10px] tracking-[0.14em]",
            camera.captureState === "LIVE"
              ? "border-destructive/50 bg-destructive/15 text-destructive"
              : "border-info/50 bg-info/15 text-info",
          )}
        >
          <Dot state={camera.captureState === "LIVE" ? "down" : "info"} />
          {camera.captureState === "LIVE" ? "CHƯA CHỤP" : "ĐÃ CHỤP"}
        </span>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 bg-gradient-to-t from-background/92 to-transparent px-2.5 py-2 font-mono text-[10px] tracking-wider text-muted-foreground">
        <span>{camera.captureState === "CAPTURED" ? "ĐÃ CHỤP" : "CHƯA CHỤP"}</span>
        <span className={camera.health === "DEGRADED" ? "text-warning" : "text-success"}>
          {camera.health === "DEGRADED" ? "PHÁT HIỆN LỖI" : "OK"}
        </span>
      </div>

      {camera.image && onZoom ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onZoom();
          }}
          className="absolute right-2 top-10 grid size-7 place-items-center rounded-sm border border-border bg-background/80 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
          aria-label={`Phóng to ${camera.id}`}
        >
          <Maximize2 className="size-3.5" />
        </button>
      ) : null}

      {camera.captureState === "LIVE" ? (
        <motion.div
          className="pointer-events-none absolute inset-0 border border-info/40"
          animate={{ opacity: [0, 0.6, 0] }}
          transition={{ duration: 2.6, repeat: Infinity }}
        />
      ) : null}
    </div>
  );
}
