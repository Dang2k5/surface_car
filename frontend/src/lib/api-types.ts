// Backend contract types, ported from the legacy frontend/app/page.tsx (kept in sync manually —
// the FastAPI backend is the source of truth, see backend/app/langgraph_schemas.py and agent/graph/state.py).

export type Role = "QC_OPERATOR" | "QC_SUPERVISOR";
export type AuthProfile = {
  user_id: string;
  email: string | null;
  full_name: string | null;
  role: Role | string;
  station_id?: string | null;
};

export type Profile = {
  user_id: string;
  email: string | null;
  full_name: string | null;
  role: Role | string;
  station_id: string | null;
  /** SQLite stores this as 0/1, Postgres as a boolean — normalise with isProfileActive. */
  active: boolean | number;
  created_at: string;
  updated_at: string;
};
export type ProfileUpdate = { role?: Role; station_id?: string | null; active?: boolean };

/** Active stations offered on the (unauthenticated) sign-up form — see
 * backend/app/catalog_api.py's list_station_options. */
export type StationOption = { station_id: string; name: string };

export type TraceEvent = { node: string; status: string; detail: string };

export type PolicyReference = Record<string, unknown>;
export type PolicyDocumentReview = Record<string, unknown>;

export type EnrichedDefect = {
  detection_id: string;
  camera_id: string;
  class_name: string;
  raw_class_name: string;
  confidence: number;
  bbox: { x1: number; y1: number; x2: number; y2: number };
  segmentation?: { format: string; points: number[][] } | null;
  zone_name: string;
  estimated_width_mm: number | null;
  estimated_height_mm: number | null;
  surface_area_mm2: number | null;
  physical_measurement_status: string;
  calibration_profile_id?: string | null;
  severity_rank: string;
  is_primary: boolean;
  overlay_image_url?: string;
  crop_image_url?: string;
  mask_image_url?: string;
  /** Set only for a video-sourced camera (backend/app/langgraph_api.py's
   * _track_camera_across_frames): every video-playback second (relative to that camera's own
   * clip) this tracked defect was actually observed in, so the player can show its box only
   * near those moments instead of burning it onto the whole clip. */
  track_timestamps?: number[];
  /** Same video-sourced-camera tracking as track_timestamps, but carrying each observation's
   * own bbox/segmentation (every extracted frame was independently inferred, not just the
   * single highest-confidence one) -- lets the player draw the mask at the position it
   * actually had nearest the current playback time instead of freezing it at one frame's
   * position for the whole tracked window. */
  track_frames?: {
    timestamp: number;
    bbox: { x1: number; y1: number; x2: number; y2: number } | null;
    segmentation?: { format: string; points: number[][] } | null;
  }[];
};

// One entry per camera that had >=1 detection — each camera's own worst finding,
// classified independently against the defect catalog + LLM (agent/graph/nodes.py's
// QCNodes._classify_local_detection). Lets the UI show WHY a specific camera's finding
// was classified the way it was, instead of only ever reading the single global-worst one.
export type CameraClassification = {
  detection_id: string;
  camera_id: string;
  defect_type: string;
  confidence: number;
  bbox: { x1: number; y1: number; x2: number; y2: number };
  visual_measurements?: Record<string, unknown>;
  suggested_defect_codes: DefectCode[];
  classified_defect_code: string | null;
  defect_family: string | null;
  catalog_defect_type: string | null;
  severity: string;
  severity_source_id: string | null;
  similar_defect_warning: boolean;
};

// Policy verdict for ONE camera's own classified finding (agent/graph/nodes.py's
// assess_result) — the vehicle's final_status is FAIL if ANY of these is FAIL.
export type CameraPolicyDecision = {
  camera_id: string;
  detection_id: string;
  policy_decision: { final_status?: string; action_code?: string; action_label?: string } & Record<
    string,
    unknown
  >;
};

export type CameraEvidence = {
  camera_id: string;
  image_path?: string;
  image_url?: string;
  /** Set only when this camera's evidence came from an uploaded video (langgraph_api.py's
   * run_uploaded_videos_inspection) — the original clip, for real video playback instead of
   * just the one representative still frame `image_url` points at. */
  video_url?: string;
};
export type CameraResult = {
  camera_id: string;
  defect_detected: boolean;
  detections?: EnrichedDefect[];
  image_width?: number;
  image_height?: number;
  video_url?: string;
  frame_tracking?: { tracked_frame_count: number; frame_interval_seconds: number };
};

export type QCDecisionRecord = {
  decision_id: string;
  inspection_id: string;
  vehicle_id: string;
  defect_code: string;
  defect_type: string;
  location: string;
  length_mm: number | null;
  severity: string;
  action: string;
  disposition: string;
  reviewer: string;
  created_at: string;
};

export type QCState = {
  thread_id: string;
  inspection_id: string;
  vehicle_id: string;
  vehicle_model: string;
  lot_id?: string | null;
  shift_id?: string | null;
  production_date?: string | null;
  station_id?: string;
  image_url: string;
  camera_id: string;
  camera_evidence?: CameraEvidence[];
  camera_results?: CameraResult[];
  zone_name: string;
  defect_detected?: boolean;
  defect_type?: string;
  confidence?: number;
  bbox?: { x1: number; y1: number; x2: number; y2: number } | null;
  segmentation_result?: { format: string; points: number[][] } | null;
  visual_measurements?: {
    relative_position: string;
    estimated_width_mm?: number;
    estimated_height_mm?: number;
    estimated_length_mm?: number;
  };
  primary_detection_id?: string | null;
  enriched_defects?: EnrichedDefect[];
  camera_classifications?: CameraClassification[];
  camera_policy_decisions?: CameraPolicyDecision[];
  unresolved_camera_ids?: string[];
  /** Every vehicle body side (front/rear/left/right/top) with a defect in this inspection —
   * one run combines all 5 fixed cameras, so more than one side can be affected at once.
   * zone_name alone only ever names the single worst one. */
  affected_zones?: string[];
  overlay_image_url?: string | null;
  crop_image_url?: string | null;
  mask_image_url?: string | null;
  image_width?: number;
  image_height?: number;
  severity?: string;
  decision?: string;
  reason?: string;
  human_required?: boolean;
  human_decision?: {
    action: string;
    reviewer: string;
    reason: string;
    recommendation?: string;
    supervisor_action?: string;
    supervisor_reviewer?: string;
    supervisor_reason?: string;
  };
  qc_decision_record?: QCDecisionRecord;
  /** The operator who submitted this inspection (backend/app/langgraph_api.py's
   * _submitter_name) — set for every run, unlike human_decision.reviewer which only exists
   * once a HITL case has been resolved. */
  submitted_by?: string | null;
  suggested_defect_codes?: DefectCode[];
  classified_defect_code?: string | null;
  defect_family?: string | null;
  defect_code_classification?: {
    confidence: number;
    rationale_vi: string;
    provider: string;
    candidate_codes: string[];
  };
  recommendation_code?: string;
  recommendation?: string;
  final_status?: string;
  allow_test_drive?: boolean;
  hitl_status?:
    "PENDING" | "CONFIRMED" | "OVERRIDDEN" | "SUPERVISOR_APPROVED" | "SUPERVISOR_REJECTED";
  execution_trace?: TraceEvent[];
  /** ISO timestamp of the last time this run was persisted (backend/app/langgraph_api.py's
   * list_agent_runs, backed by QCRepository.list_with_metadata) — used as "waiting since". */
  _persisted_at?: string;
};

export type GraphRun = {
  thread_id: string;
  status: "COMPLETED" | "INTERRUPTED";
  state: QCState;
  interrupt?: { reason?: string; allowed_actions?: string[] };
};

export type GraphSpec = { nodes: string[]; checkpointer: string; mermaid: string };

export type RuntimeStatus = {
  mode: string;
  provider?: string | null;
  configured?: boolean;
  llm_accessed?: boolean;
  last_call_status?: string;
};

export type AgentStatus = {
  langgraph: string;
  checkpointer: string;
  reasoning: {
    mode: string;
    provider: string;
    api_key_configured: boolean;
    llm_accessed: boolean;
    last_call_status: string;
  };
  vision?: RuntimeStatus;
  object_storage?: { mode: string; provider?: string; bucket?: string; configured?: boolean };
};

export type TrendRow = {
  group_by: string;
  group_value: string;
  total_inspections: number;
  scratch_count: number;
  dent_count: number;
  pass_count: number;
  fail_count: number;
  scratch_rate: number;
  dent_rate: number;
  pass_fail_rate: number;
};

// Defect classification catalog (backend/app/qc_api.py's /api/qc/defect-codes) — the
// severity A/B/C thresholds every inspection is classified against. source_id/source_title/
// source_document_status trace back to the controlled-policy source register
// (agent/policies/qc_policy_catalog.json) that justifies default_severity/classification_rule;
// document_status !== "APPROVED" means that threshold is still an unapproved working draft.
// rule_type/min_mm/max_mm/min_detection_count are the structured counterpart to
// classification_rule that agent/services/defect_rule_engine.py actually evaluates to
// auto-select a code (classification_rule stays free text, for humans to read). A code
// with rule_type null/undefined can never auto-match -- the rule engine always routes it
// to HITL instead of guessing.
export type DefectCodeRuleType = "THRESHOLD_MM" | "MIN_COUNT" | "REQUIRES_HUMAN";

export type DefectCode = {
  defect_code: string;
  defect_type: string;
  cv_label: string;
  defect_family: string;
  display_name: string;
  description: string;
  classification_rule: string;
  default_severity: string;
  measurement_required: number;
  active: number;
  source_id: string | null;
  source_title: string | null;
  source_document_status: string | null;
  rule_type: DefectCodeRuleType | null;
  min_mm: number | null;
  max_mm: number | null;
  min_detection_count: number | null;
};

export type QualityAlert = {
  id: string;
  severity: "WATCH" | "WARNING" | "CRITICAL";
  status: string;
  defect_type: string;
  zone_name: string;
  camera_id: string;
  occurrence_count: number;
  affected_vehicle_count: number;
  affected_vehicle_ids: string[];
  related_defect_codes: string[];
  average_confidence: number;
  maximum_confidence: number;
  first_seen: string;
  last_seen: string;
  window_hours: number;
  window_size: number;
  consecutive_count: number;
  trigger_type: string;
  predicted_root_cause: string;
  root_cause_evidence: "COORDINATE_CLUSTER_CONFIRMED" | "ZONE_ONLY_UNCONFIRMED";
  root_cause_evidence_detail: {
    coordinate_cluster: boolean;
    single_camera: boolean;
    severity_at_least_warning: boolean;
    occurrence_count: number;
  };
  upstream_target_shop: string;
  actionable_routing_command: string;
  message_en: string;
  message_vi: string;
  recommendation_en: string;
  recommendation_vi: string;
  upstream_checks_en: string[];
  upstream_checks_vi: string[];
};

export type QualityAlertSummary = {
  generated_at: string;
  window_hours: number;
  window_size: number;
  watch_consecutive_threshold: number;
  watch_window_threshold: number;
  minimum_occurrences: number;
  in_window_threshold: number;
  critical_consecutive_threshold: number;
  critical_window_threshold: number;
  alerts: QualityAlert[];
};

export type ResumeAction = "APPROVE" | "REJECT" | "OVERRIDE";
// Second HITL gate only (supervisor_review): either uphold the automated policy decision,
// or apply one specific APPROVED catalog policy id as the case's final disposition.
export type SupervisorResumeAction = "UPHOLD_POLICY" | (string & {});
export type ResumePayload = {
  action: ResumeAction | SupervisorResumeAction;
  reviewer: string;
  reason: string;
  defect_code?: string;
  severity?: string;
  disposition?: "PASS" | "HOLD" | "REPAIR";
  location?: string;
  length_mm?: number;
  notes?: string;
  recommendation?: string;
  // Required instead of defect_code when the case has more than one unresolved finding
  // (backend/app/langgraph_schemas.py's DetectionResolution) -- one defect_code per
  // detection_id, so each finding gets its own real classification.
  detection_resolutions?: { detection_id: string; defect_code: string; severity?: string }[];
};

export type SubmitSingleInspection = {
  file: File;
  vehicleId: string;
  vehicleModel: string;
  cameraId: string;
  lotId?: string;
  shiftId?: string;
  productionDate?: string;
  stationId?: string;
};

export type SubmitMultiInspection = Omit<SubmitSingleInspection, "file" | "cameraId"> & {
  cameras: { file: File; cameraId: string }[];
};

// Ca làm việc / Lô sản xuất catalogs (backend/app/catalog_api.py) — QC_SUPERVISOR manages these;
// the inspection upload form (routes/inspection.tsx) picks from the active list only.
export type Shift = {
  shift_id: string;
  name: string;
  start_time: string;
  end_time: string;
  active: boolean | number;
  created_at: string;
  updated_at: string;
};

export type ShiftCreate = {
  shift_id: string;
  name: string;
  start_time?: string;
  end_time?: string;
};
export type ShiftUpdate = Partial<Pick<Shift, "name" | "start_time" | "end_time">> & {
  active?: boolean;
};

// A lot is produced during one shift, at one station — Trạm/Ca stay independent catalogs
// (a shift runs in parallel across multiple stations), the lot references which Trạm+Ca
// it was produced under.
export type ProductionLot = {
  lot_id: string;
  name: string;
  note: string;
  station_id: string | null;
  shift_id: string | null;
  product_model: string;
  quantity: number;
  active: boolean | number;
  created_at: string;
  updated_at: string;
};

export type LotCreate = {
  lot_id: string;
  name: string;
  station_id: string;
  shift_id: string;
  product_model: string;
  quantity: number;
  note?: string;
};
export type LotUpdate = {
  name?: string;
  note?: string;
  station_id?: string;
  shift_id?: string;
  product_model?: string;
  quantity?: number;
  active?: boolean;
};

// A product code is allocated one at a time as a vehicle passes the camera during an
// inspection (backend/app/database.py Database.allocate_lot_product), format:
// <Mã Lô>-<Model sản phẩm>-<STT>, STT starting at 1 and counting up until quantity is used.
export type LotProduct = {
  product_code: string;
  lot_id: string;
  seq: number;
  vehicle_model: string;
  created_at: string;
};

export type LotProductAllocate = { vehicle_model: string };

export type Station = {
  station_id: string;
  name: string;
  active: boolean | number;
  created_at: string;
  updated_at: string;
};

export type StationCreate = { station_id: string; name: string };
export type StationUpdate = { name?: string; active?: boolean };

export type DefectCodeCreate = {
  defect_code: string;
  defect_type: "scratch" | "dent";
  cv_label: "scratch" | "dent";
  defect_family?: string;
  display_name: string;
  description?: string;
  classification_rule?: string;
  default_severity?: string;
  measurement_required?: boolean;
  source_id?: string;
  active?: boolean;
  rule_type?: DefectCodeRuleType;
  min_mm?: number;
  max_mm?: number;
  min_detection_count?: number;
};

export type DefectCodeUpdate = {
  defect_family?: string;
  display_name?: string;
  description?: string;
  classification_rule?: string;
  default_severity?: string;
  measurement_required?: boolean;
  source_id?: string;
  active?: boolean;
  rule_type?: DefectCodeRuleType;
  min_mm?: number;
  max_mm?: number;
  min_detection_count?: number;
};

// QC_SUPERVISOR-facing types, ported from the legacy quality-command-61 (Lovable) frontend —
// mapped onto the real backend contracts below instead of that project's mock qc-data.ts.

export type PolicySource = {
  id: string;
  document_family: string;
  revision: string;
  section: string;
  effective_date: string | null;
  expiry_date: string | null;
  document_status: string;
  authority?: string;
  title: string;
  scope: string;
  url: string;
};

export type PolicyCatalogItem = {
  id: string;
  title: string;
  applicability: { vehicle_models: string[] };
  conditions: string[];
  checklist_status: string;
  defect_types: string[];
  action_code?: string;
  action_code_by_defect?: Record<string, string>;
  final_status: string;
  test_drive_allowed: boolean;
  human_required: boolean;
  required_evidence: string[];
  steps: string[];
  source_ids: string[];
};

export type PolicyItemCreate = {
  id: string;
  title: string;
  applicability?: { vehicle_models: string[] };
  conditions?: string[];
  checklist_status?: "DRAFT" | "APPROVED";
  defect_types: string[];
  action_code?: string;
  action_code_by_defect?: Record<string, string>;
  final_status: string;
  test_drive_allowed?: boolean | null;
  human_required?: boolean;
  required_evidence?: string[];
  steps?: string[];
  source_ids?: string[];
};

export type PolicyItemUpdate = Partial<Omit<PolicyItemCreate, "id">>;

export type PolicyExtractionResult = {
  policy_draft: {
    suggested_id: string;
    title: string;
    defect_types: string[];
    conditions: string[];
    required_evidence: string[];
    steps: string[];
    action_code: string;
    final_status: string;
    test_drive_allowed: boolean | null;
    human_required: boolean;
  };
  source_draft: {
    document_family: string;
    revision: string;
    title: string;
    section: string;
    effective_date: string | null;
  };
  extraction_notes_vi: string;
  provider: string;
  model: string;
};

export type PolicyCatalog = {
  catalog_id: string;
  revision: string;
  status: string;
  approval_scope: string;
  effective_date: string;
  owner: string;
  disclaimer: string;
  sources: PolicySource[];
  policies: PolicyCatalogItem[];
};

export type QcDecision = {
  decision_id: string;
  thread_id: string | null;
  inspection_id: string;
  vehicle_id: string;
  defect_code: string;
  defect_type: string;
  location: string;
  length_mm: number | null;
  severity: string;
  action: "APPROVE" | "REJECT" | "OVERRIDE";
  disposition: "PASS" | "HOLD" | "REPAIR";
  reviewer: string;
  reason: string;
  notes: string;
  created_at: string;
};
