// Backend contract types, ported from the legacy frontend/app/page.tsx (kept in sync manually —
// the FastAPI backend is the source of truth, see backend/app/langgraph_schemas.py and agent/graph/state.py).

export type Role = "QC_OPERATOR" | "QC_SUPERVISOR";
export type AuthProfile = { user_id: string; email: string | null; role: Role | string };

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
};

export type CameraEvidence = { camera_id: string; image_path?: string; image_url?: string };
export type CameraResult = {
  camera_id: string;
  defect_detected: boolean;
  detections?: EnrichedDefect[];
  image_width?: number;
  image_height?: number;
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
};

export type QualityAlert = {
  id: string;
  severity: "WARNING" | "CRITICAL";
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
  upstream_target_shop: string;
  actionable_routing_command: string;
  message_en: string;
  message_vi: string;
};

export type QualityAlertSummary = {
  generated_at: string;
  window_hours: number;
  alerts: QualityAlert[];
};

export type ResumeAction = "APPROVE" | "REJECT" | "OVERRIDE";
export type ResumePayload = {
  action: ResumeAction;
  reviewer: string;
  reason: string;
  defect_code?: string;
  severity?: string;
  disposition?: "PASS" | "HOLD" | "REWORK" | "REINSPECT";
  location?: string;
  length_mm?: number;
  notes?: string;
  recommendation?: string;
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
  note: string;
  station_id: string | null;
  shift_id: string | null;
  vehicle_type: string;
  quantity: number;
  active: boolean | number;
  created_at: string;
  updated_at: string;
};

export type LotCreate = {
  lot_id: string;
  station_id: string;
  shift_id: string;
  vehicle_type: string;
  quantity: number;
  note?: string;
};
export type LotUpdate = {
  note?: string;
  station_id?: string;
  shift_id?: string;
  quantity?: number;
  active?: boolean;
};

// Auto-generated per-vehicle product code for a lot: <vehicle_type><stt>, stt from 1..quantity
// (backend/app/database.py Database._generate_lot_products).
export type LotProduct = {
  product_code: string;
  lot_id: string;
  seq: number;
  vehicle_type: string;
  created_at: string;
};

export type Station = {
  station_id: string;
  name: string;
  active: boolean | number;
  created_at: string;
  updated_at: string;
};

export type StationCreate = { station_id: string; name: string };
export type StationUpdate = { name?: string; active?: boolean };

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
  disposition: "PASS" | "HOLD" | "REWORK" | "REINSPECT";
  reviewer: string;
  reason: string;
  notes: string;
  created_at: string;
};
