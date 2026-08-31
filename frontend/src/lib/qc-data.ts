export type Verdict = "PASS" | "FAIL" | "HITL";
export type Severity = "Minor" | "Medium" | "Major" | "Critical";
export type WarningLevel = "WATCH" | "WARNING" | "CRITICAL";

export type CameraId = "CAM-01" | "CAM-02" | "CAM-03" | "CAM-04" | "CAM-05";
export const KNOWN_CAMERA_IDS: CameraId[] = ["CAM-01", "CAM-02", "CAM-03", "CAM-04", "CAM-05"];

export type Camera = {
  id: CameraId;
  position: string;
  captureState: "LIVE" | "CAPTURED";
  /** Empty string when this camera has no uploaded evidence yet — render a placeholder, not a stock photo. */
  image: string;
  health: "OK" | "DEGRADED";
  /**
   * The captured photo's own pixel resolution, when known. CameraFeed needs this to size its
   * letterbox wrapper so the % box/mask overlay (computed against these same pixel dimensions in
   * detection-geometry.ts) lands on the real defect instead of drifting when the photo's aspect
   * ratio doesn't match the fixed card aspect ratio.
   */
  imageWidth?: number | undefined;
  imageHeight?: number | undefined;
  /** Set only when this camera's evidence is an uploaded video clip — CameraFeed renders a
   * real <video> player (poster = `image`) instead of a static <img> when present. */
  videoUrl?: string | undefined;
};

export type Defect = {
  id: string;
  index: number;
  type: "Scratch" | "Dent" | "Surface anomaly";
  location: string;
  severity: Severity;
  confidence: number;
  camera: CameraId;
  measurement: string;
  threshold: string;
  decision: "FAIL" | "PASS";
  /** bounding box in % of the camera frame */
  box: { x: number; y: number; w: number; h: number };
  /** YOLO segmentation mask outline in % of the camera frame, when the model returned one */
  polygon?: { x: number; y: number }[] | undefined;
  /** Rendered PNGs for THIS detection specifically (FR-17) — undefined when rendering hasn't
   * run yet or failed for this detection, not just for the run's primary finding. */
  cropImageUrl?: string | undefined;
  overlayImageUrl?: string | undefined;
  /** Set only for a video-sourced camera — playback seconds (relative to that camera's own
   * clip) this tracked defect was actually observed in. When set, CameraFeed only shows this
   * defect's box while the video's current time is near one of these moments. */
  trackTimestamps?: number[] | undefined;
};

export type HistoryRow = {
  time: string;
  vin: string;
  model: string;
  result: Verdict;
  defects: number;
  confidence: number;
  severity: Severity | "—";
  defectType: string;
};
