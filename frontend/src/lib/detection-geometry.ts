import {
  KNOWN_CAMERA_IDS,
  type Camera,
  type CameraId,
  type Defect,
  type Severity,
} from "@/lib/qc-data";
import type {
  CameraClassification,
  CameraPolicyDecision,
  EnrichedDefect,
  QCState,
} from "@/lib/api-types";
import { assetUrl } from "@/lib/auth";

// Static position labels for the 5 fixed camera mounts — not sample/demo data, just UI copy
// (the backend has no camera-position catalog; there's nothing else to name these slots from).
export const CAMERA_POSITION_LABELS: Record<CameraId, string> = {
  "CAM-01": "TRƯỚC",
  "CAM-02": "SAU",
  "CAM-03": "TRÁI",
  "CAM-04": "PHẢI",
  "CAM-05": "TRÊN / TOÀN CẢNH",
};

export function camerasFromState(state: QCState | undefined): Camera[] {
  return KNOWN_CAMERA_IDS.map((id) => {
    const evidence = state?.camera_evidence?.find((e) => e.camera_id === id);
    const result = state?.camera_results?.find((r) => r.camera_id === id);
    return {
      id,
      position: CAMERA_POSITION_LABELS[id],
      // No fallback to a stock photo here — an uncaptured camera shows an empty slot, not a
      // sample image pretending to be real evidence.
      image: assetUrl(evidence?.image_url || evidence?.image_path) || "",
      captureState: evidence ? "CAPTURED" : "LIVE",
      health: result?.defect_detected ? "DEGRADED" : "OK",
      imageWidth: result?.image_width,
      imageHeight: result?.image_height,
      videoUrl: assetUrl(evidence?.video_url || result?.video_url) || undefined,
    };
  });
}

// The CV model's taxonomy (agent/services/yolo_detector.py's CLASS_MAP) only ever normalizes
// to "scratch" or "dent" — map those onto the small closed set the UI badge uses. Anything else
// (a class the map hasn't been taught yet) falls back to "Surface anomaly" rather than crashing.
export function mapDefectType(className: string): Defect["type"] {
  const key = className.toLowerCase();
  if (key.includes("scratch")) return "Scratch";
  if (key.includes("dent")) return "Dent";
  return "Surface anomaly";
}

// Real severity codes come from the QC defect catalog (backend/app/database.py: default_severity
// column) as single letters — A = most severe, B = medium, C = minor — not the "critical/major/
// minor" words this used to look for, so those never matched real backend data. UNASSESSED /
// UNCONFIRMED / NONE fall back to "Medium" until a human or the agent
// finishes classifying the finding.
export function mapSeverity(severityRank: string | undefined): Severity {
  const key = (severityRank || "").trim().toUpperCase();
  if (key === "A" || key.includes("CRIT")) return "Critical";
  if (key === "B" || key.includes("MAJOR") || key.includes("HIGH")) return "Major";
  if (key === "C" || key.includes("MINOR") || key.includes("LOW")) return "Minor";
  return "Medium";
}

// zone_name is a fixed vehicle body side (agent/graph/nodes.py's _CAMERA_ZONE_NAMES) — each of
// the 5 camera mounts is physically fixed to photograph one specific side of the vehicle, so
// which camera saw a defect really does tell you which side it's on.
const ZONE_LABEL_VI: Record<string, string> = {
  truoc: "Trước",
  sau: "Sau",
  trai: "Trái",
  phai: "Phải",
  tren_toan_canh: "Trên / Toàn cảnh",
};

export function formatZoneName(zone: string | undefined): string {
  if (!zone || zone === "unknown_zone") return "—";
  return ZONE_LABEL_VI[zone] || zone;
}

// One inspection combines all 5 fixed cameras, so it can have simultaneous defects on more
// than one side of the vehicle — join every affected zone instead of showing only one.
export function formatAffectedZones(zones: string[] | undefined): string {
  if (!zones || zones.length === 0) return "—";
  return zones.map(formatZoneName).join(", ");
}

export const SEVERITY_LABEL_VI: Record<Severity, string> = {
  Critical: "Nghiêm trọng",
  Major: "Nặng",
  Medium: "Trung bình",
  Minor: "Nhẹ",
};

// Backend bboxes are pixel coordinates (x1,y1,x2,y2); CameraFeed expects percent-of-frame {x,y,w,h}.
export function bboxToPercentBox(
  bbox: { x1: number; y1: number; x2: number; y2: number } | null | undefined,
  imageWidth: number | undefined,
  imageHeight: number | undefined,
): Defect["box"] {
  if (!bbox || !imageWidth || !imageHeight) return { x: 0, y: 0, w: 0, h: 0 };
  return {
    x: (bbox.x1 / imageWidth) * 100,
    y: (bbox.y1 / imageHeight) * 100,
    w: ((bbox.x2 - bbox.x1) / imageWidth) * 100,
    h: ((bbox.y2 - bbox.y1) / imageHeight) * 100,
  };
}

// The YOLO detector (agent/services/yolo_detector.py) is a segmentation model — it always returns
// a polygon mask outline (pixel coords) alongside the bbox. Convert those points to percent-of-
// frame so CameraFeed can draw the real mask instead of just its bounding rectangle.
export function segmentationToPercentPoints(
  segmentation: { format: string; points: number[][] } | null | undefined,
  imageWidth: number | undefined,
  imageHeight: number | undefined,
): Defect["polygon"] {
  if (!segmentation?.points?.length || !imageWidth || !imageHeight) return undefined;
  return segmentation.points.map((point) => ({
    x: ((point[0] ?? 0) / imageWidth) * 100,
    y: ((point[1] ?? 0) / imageHeight) * 100,
  }));
}

// Every detection gets its own independent classification (agent/graph/nodes.py's
// QCNodes._classify_local_detection, one call per detection — see
// state.camera_classifications). A finding with no match here (e.g. an inference error,
// or a truly unclassifiable CV label) has no real threshold/rule to show; showing another
// finding's rule on it would misattribute that finding's size bucket.
// classification_rule (agent/services/defect_catalog.py) is a condition expression meant for
// the policy engine, e.g. "25 < estimated_width_mm <= 50" or "at least 2 dent detections" — not
// display copy. QC only needs the numeric bound(s) that decide the size class, not the full
// "when to pick this" sentence, so pull just the number(s)/unit out of it.
const COMPARATOR_SYMBOL: Record<string, string> = { "<=": "≤", ">=": "≥", "<": "<", ">": ">" };

function numericThresholdFromRule(rule: string): string {
  const mm = rule.match(
    /^(?:(\d+(?:\.\d+)?)\s*<\s*estimated_width_mm\s*<=\s*(\d+(?:\.\d+)?)|estimated_width_mm\s*(<=|<|>=|>)\s*(\d+(?:\.\d+)?))$/,
  );
  if (mm) {
    if (mm[1] && mm[2]) return `${mm[1]}–${mm[2]} mm`;
    return `${COMPARATOR_SYMBOL[mm[3]!]} ${mm[4]} mm`;
  }
  const count = rule.match(/^at least (\d+)/i);
  if (count) return `≥ ${count[1]}`;
  const ratio = rule.match(/aspect ratio\s*(<=|<|>=|>)\s*(\d+(?:\.\d+)?)/i);
  if (ratio) return `${COMPARATOR_SYMBOL[ratio[1]!]} ${ratio[2]}`;
  return "—";
}

function thresholdFor(
  d: EnrichedDefect,
  cameraClassifications: CameraClassification[] | undefined,
): string {
  const own = cameraClassifications?.find((c) => c.detection_id === d.detection_id);
  if (!own?.classified_defect_code) return "—";
  const rule = own.suggested_defect_codes.find((c) => c.defect_code === own.classified_defect_code)
    ?.classification_rule;
  return rule ? numericThresholdFromRule(rule) : "—";
}

// The vehicle-level final_status is a single PASS/FAIL, but each finding was
// policy-evaluated independently (agent/graph/nodes.py's assess_result, state.camera_policy_
// decisions) — show THAT finding's own verdict when it exists instead of blindly copying the
// overall vehicle verdict onto every finding (which would hide a PASS-eligible finding behind
// a different finding's FAIL, or vice versa).
function decisionFor(
  d: EnrichedDefect,
  cameraPolicyDecisions: CameraPolicyDecision[] | undefined,
  overallDecision: "PASS" | "FAIL",
): "PASS" | "FAIL" {
  const own = cameraPolicyDecisions?.find((c) => c.detection_id === d.detection_id);
  const ownStatus = own?.policy_decision?.final_status;
  return ownStatus === "PASS" || ownStatus === "FAIL" ? ownStatus : overallDecision;
}

function toDefect(
  d: EnrichedDefect,
  index: number,
  overallDecision: "PASS" | "FAIL",
  imageWidth: number | undefined,
  imageHeight: number | undefined,
  cameraClassifications: CameraClassification[] | undefined,
  cameraPolicyDecisions: CameraPolicyDecision[] | undefined,
): Defect {
  const camera = (KNOWN_CAMERA_IDS.includes(d.camera_id as CameraId)
    ? d.camera_id
    : "CAM-01") as CameraId;
  return {
    id: d.detection_id,
    index: index + 1,
    type: mapDefectType(d.class_name),
    // The backend's zone_name is an internal token (e.g. "unknown_zone" when a caller never
    // picks one) and not fit for display — the camera mount position is the real, always-known
    // location of a finding, so show that instead of trusting zone_name to be meaningful.
    location: CAMERA_POSITION_LABELS[camera],
    severity: mapSeverity(d.severity_rank),
    // Backend confidence is a 0-1 fraction; UI displays a percent.
    confidence: Math.round(d.confidence * 1000) / 10,
    camera,
    measurement: d.estimated_width_mm != null ? `${d.estimated_width_mm.toFixed(1)} mm` : "—",
    threshold: thresholdFor(d, cameraClassifications),
    decision: decisionFor(d, cameraPolicyDecisions, overallDecision),
    box: bboxToPercentBox(d.bbox, imageWidth, imageHeight),
    polygon: segmentationToPercentPoints(d.segmentation, imageWidth, imageHeight),
    cropImageUrl: assetUrl(d.crop_image_url) || undefined,
    overlayImageUrl: assetUrl(d.overlay_image_url) || undefined,
    trackTimestamps: d.track_timestamps,
  };
}

export function defectsFromState(state: QCState | undefined): Defect[] {
  if (!state?.enriched_defects?.length) return [];
  const overallPass = state.final_status === "PASS";
  return state.enriched_defects.map((d, i) => {
    // Each camera photo has its own resolution (agent/services/yolo_detector.py builds bbox/mask
    // pixel coordinates per-camera). state.image_width/height only reflect the PRIMARY camera's
    // photo, so normalizing every defect's coordinates against it misaligns the box/mask on any
    // other camera view. Prefer the matching camera_results entry's own dimensions instead.
    const cameraResult = state.camera_results?.find((r) => r.camera_id === d.camera_id);
    const imageWidth = cameraResult?.image_width ?? state.image_width;
    const imageHeight = cameraResult?.image_height ?? state.image_height;
    return toDefect(
      d,
      i,
      overallPass ? "PASS" : "FAIL",
      imageWidth,
      imageHeight,
      state.camera_classifications,
      state.camera_policy_decisions,
    );
  });
}
