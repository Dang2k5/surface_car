import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Minus, Plus, RotateCcw, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Defect } from "@/lib/qc-data";

const MIN_SCALE = 1;
const MAX_SCALE = 4;
const SCALE_STEP = 0.5;

export function ImageLightbox({
  src,
  alt,
  defects,
  onClose,
}: {
  src: string;
  alt: string;
  /** Box/polygon overlay drawn on top of the image, in the same % coordinates as CameraFeed. */
  defects?: Defect[] | undefined;
  onClose: () => void;
}) {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const zoomIn = () => setScale((s) => Math.min(MAX_SCALE, +(s + SCALE_STEP).toFixed(2)));
  const zoomOut = () => setScale((s) => Math.max(MIN_SCALE, +(s - SCALE_STEP).toFixed(2)));
  const reset = () => setScale(1);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex flex-col bg-background/95 backdrop-blur"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="flex items-center justify-end gap-2 border-b border-border px-4 py-2"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={zoomOut}
          disabled={scale <= MIN_SCALE}
          className="grid size-8 place-items-center rounded-sm border border-border text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
          aria-label="Thu nhỏ"
        >
          <Minus className="size-4" />
        </button>
        <span className="w-14 text-center font-mono text-xs text-muted-foreground">
          {Math.round(scale * 100)}%
        </span>
        <button
          type="button"
          onClick={zoomIn}
          disabled={scale >= MAX_SCALE}
          className="grid size-8 place-items-center rounded-sm border border-border text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
          aria-label="Phóng to"
        >
          <Plus className="size-4" />
        </button>
        <button
          type="button"
          onClick={reset}
          className="grid size-8 place-items-center rounded-sm border border-border text-muted-foreground transition-colors hover:text-foreground"
          aria-label="Đặt lại kích thước"
        >
          <RotateCcw className="size-4" />
        </button>
        <button
          type="button"
          onClick={onClose}
          className="grid size-8 place-items-center rounded-sm border border-border text-muted-foreground transition-colors hover:border-destructive/50 hover:text-destructive"
          aria-label="Đóng"
        >
          <X className="size-4" />
        </button>
      </div>
      <div
        className="flex flex-1 items-center justify-center overflow-auto p-6"
        onClick={(e) => e.stopPropagation()}
        onWheel={(e) => {
          e.preventDefault();
          if (e.deltaY < 0) zoomIn();
          else zoomOut();
        }}
      >
        <div
          className={cn("relative inline-block", scale > MIN_SCALE && "cursor-grab")}
          style={{ transform: `scale(${scale})`, transition: "transform 0.15s ease-out" }}
        >
          <img
            src={src}
            alt={alt}
            draggable={false}
            className="block max-h-[85vh] max-w-[90vw] select-none object-contain"
          />
          {defects && defects.length > 0 ? (
            <>
              <svg
                className="pointer-events-none absolute inset-0 h-full w-full"
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
              >
                {defects
                  .filter((d) => d.polygon && d.polygon.length >= 3)
                  .map((d) => (
                    <polygon
                      key={d.id}
                      points={d.polygon!.map((p) => `${p.x},${p.y}`).join(" ")}
                      vectorEffect="non-scaling-stroke"
                      className={
                        d.decision === "FAIL"
                          ? "fill-destructive/20 stroke-destructive stroke-[2]"
                          : "fill-warning/20 stroke-warning stroke-[2]"
                      }
                    />
                  ))}
              </svg>
              {defects.map((d) => {
                // A segmentation mask polygon is already drawn above; don't also outline the same
                // finding with its bounding box, or every masked defect shows a redundant
                // rectangle "framing" the mask. Keep the box only as a label anchor when there's
                // no mask to draw (matches CameraFeed's DefectOverlay).
                const hasMask = !!d.polygon && d.polygon.length >= 3;
                return (
                  <div
                    key={d.id}
                    className={cn(
                      "absolute",
                      hasMask
                        ? "border border-transparent"
                        : cn(
                            "border-2",
                            d.decision === "FAIL" ? "border-destructive" : "border-warning",
                          ),
                    )}
                    style={{
                      left: `${d.box.x}%`,
                      top: `${d.box.y}%`,
                      width: `${d.box.w}%`,
                      height: `${d.box.h}%`,
                    }}
                  >
                    <span
                      className={cn(
                        "absolute -top-6 left-0 whitespace-nowrap px-1.5 font-mono text-xs font-semibold tracking-wider text-background",
                        d.decision === "FAIL" ? "bg-destructive/85" : "bg-warning/85",
                      )}
                    >
                      {d.type.toUpperCase()} #{String(d.index).padStart(2, "0")} · {d.confidence}%
                    </span>
                  </div>
                );
              })}
            </>
          ) : null}
        </div>
      </div>
    </div>,
    document.body,
  );
}
