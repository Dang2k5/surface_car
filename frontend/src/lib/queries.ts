import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API_BASE, useAuth } from "./auth";
import type {
  AgentStatus,
  DefectCode,
  DefectCodeCreate,
  DefectCodeUpdate,
  GraphRun,
  GraphSpec,
  LotCreate,
  LotProduct,
  LotProductAllocate,
  LotUpdate,
  PolicyCatalog,
  PolicyExtractionResult,
  PolicyItemCreate,
  PolicyItemUpdate,
  Profile,
  ProfileUpdate,
  ProductionLot,
  QcDecision,
  QualityAlertSummary,
  ResumePayload,
  Shift,
  ShiftCreate,
  ShiftUpdate,
  Station,
  StationCreate,
  StationOption,
  StationUpdate,
  SubmitMultiInspection,
  SubmitSingleInspection,
  TrendRow,
} from "./api-types";

async function errorMessage(response: Response): Promise<string> {
  const text = await response.text().catch(() => "");
  try {
    const body: unknown = JSON.parse(text);
    if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // Not JSON — fall through to the raw text.
  }
  return text || `Yêu cầu thất bại (${response.status}).`;
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

export function useAgentStatus() {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["agent", "status"],
    queryFn: () => authedFetch("/agent/status").then((r) => json<AgentStatus>(r)),
    refetchInterval: 10_000,
  });
}

export function useAgentGraph() {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["agent", "graph"],
    queryFn: () => authedFetch("/agent/graph").then((r) => json<GraphSpec>(r)),
    staleTime: 60_000,
  });
}

export function useAgentRuns() {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["agent", "runs"],
    queryFn: () => authedFetch("/agent/runs").then((r) => json<GraphRun[]>(r)),
    refetchInterval: 5_000,
  });
}

export function useQualityAlerts() {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["quality-alerts"],
    queryFn: () => authedFetch("/api/quality-alerts").then((r) => json<QualityAlertSummary>(r)),
    refetchInterval: 10_000,
  });
}

export type TrendFilters = {
  shiftId?: string;
  lotId?: string;
  stationId?: string;
  dateFrom?: string;
  dateTo?: string;
};

function trendQueryString(groupBy: string, filters: TrendFilters = {}): string {
  const params = new URLSearchParams({ group_by: groupBy });
  if (filters.shiftId) params.set("shift_id", filters.shiftId);
  if (filters.lotId) params.set("lot_id", filters.lotId);
  if (filters.stationId) params.set("station_id", filters.stationId);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  return params.toString();
}

export function useTrend(groupBy: "hour" | "shift" | "lot" | "day", filters: TrendFilters = {}) {
  const { authedFetch, role } = useAuth();
  return useQuery({
    queryKey: ["trend", groupBy, filters],
    queryFn: () =>
      authedFetch(`/api/trend?${trendQueryString(groupBy, filters)}`).then((r) =>
        json<TrendRow[]>(r),
      ),
    enabled: role === "QC_SUPERVISOR",
    staleTime: 30_000,
  });
}

export function useDownloadTrendReport() {
  const { authedFetch } = useAuth();
  return useMutation({
    mutationFn: async ({
      groupBy,
      filters,
    }: {
      groupBy: "hour" | "shift" | "lot" | "day";
      filters: TrendFilters;
    }) => {
      const response = await authedFetch(
        `/api/trend/report.docx?${trendQueryString(groupBy, filters)}`,
      );
      if (!response.ok) {
        throw new Error(await errorMessage(response));
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "bao-cao-chat-luong.docx";
      link.click();
      URL.revokeObjectURL(url);
    },
  });
}

export function useSubmitInspection() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: SubmitSingleInspection | SubmitMultiInspection) => {
      const form = new FormData();
      const isMulti = "cameras" in payload;

      // Detect file type (image vs video)
      let isVideo = false;
      if (isMulti) {
        for (const cam of payload.cameras) {
          form.append("files", cam.file);
          form.append("camera_ids", cam.cameraId);
          if (cam.file.type.startsWith("video/")) isVideo = true;
        }
      } else {
        form.append("file", payload.file);
        form.append("camera_id", payload.cameraId);
        if (payload.file.type.startsWith("video/")) isVideo = true;
      }
      form.append("vehicle_id", payload.vehicleId);
      form.append("vehicle_model", payload.vehicleModel);
      if (payload.stationId) form.append("station_id", payload.stationId);
      if (payload.lotId) form.append("lot_id", payload.lotId);
      if (payload.shiftId) form.append("shift_id", payload.shiftId);
      if (payload.productionDate) form.append("production_date", payload.productionDate);

      // Select endpoint based on file type
      let endpoint = "/inspections/from-image";
      if (isMulti && isVideo) endpoint = "/inspections/from-videos";
      else if (isMulti) endpoint = "/inspections/from-images";
      else if (isVideo) endpoint = "/inspections/from-video";

      const response = await authedFetch(
        endpoint,
        {
          method: "POST",
          body: form,
        },
        120_000,  // Increased timeout for video processing
      );
      return json<GraphRun>(response);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agent", "runs"] });
      void queryClient.invalidateQueries({ queryKey: ["quality-alerts"] });
      void queryClient.invalidateQueries({ queryKey: ["agent", "status"] });
    },
  });
}

export function useResumeInspection() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ threadId, payload }: { threadId: string; payload: ResumePayload }) => {
      const response = await authedFetch(`/inspections/${threadId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<GraphRun>(response);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agent", "runs"] });
      void queryClient.invalidateQueries({ queryKey: ["quality-alerts"] });
    },
  });
}

export function usePolicyCatalog() {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["policies", "catalog"],
    queryFn: () => authedFetch("/api/policies").then((r) => json<PolicyCatalog>(r)),
    staleTime: 60_000,
  });
}

export function useCreatePolicy() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PolicyItemCreate) => {
      const response = await authedFetch("/api/policies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<PolicyItemCreate>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["policies", "catalog"] }),
  });
}

export function useExtractPolicyDraft() {
  const { authedFetch } = useAuth();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const response = await authedFetch(
        "/api/policies/extract",
        { method: "POST", body: form },
        60_000,
      );
      return json<PolicyExtractionResult>(response);
    },
  });
}

export function useCreateSource() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      file,
      fields,
    }: {
      file: File;
      fields: PolicyExtractionResult["source_draft"] & { id: string };
    }) => {
      // Multipart on purpose: this is the only moment the uploaded document is
      // written to object storage, so a supervisor who never saves the AI draft
      // never leaves an orphaned file behind (see backend/app/policy_api.py).
      const form = new FormData();
      form.append("file", file);
      for (const [key, value] of Object.entries(fields)) {
        if (value !== null && value !== undefined) form.append(key, value);
      }
      const response = await authedFetch(
        "/api/policies/sources",
        { method: "POST", body: form },
        60_000,
      );
      return json<PolicyExtractionResult["source_draft"] & { id: string }>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["policies", "catalog"] }),
  });
}

export function useUpdatePolicy() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ policyId, payload }: { policyId: string; payload: PolicyItemUpdate }) => {
      const response = await authedFetch(`/api/policies/${encodeURIComponent(policyId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<PolicyItemUpdate>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["policies", "catalog"] }),
  });
}

export function useDeletePolicy() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (policyId: string) => {
      const response = await authedFetch(`/api/policies/${encodeURIComponent(policyId)}`, {
        method: "DELETE",
      });
      if (!response.ok && response.status !== 204) {
        throw new Error(await errorMessage(response));
      }
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["policies", "catalog"] }),
  });
}

export function useQcDecisions(inspectionId?: string) {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["qc", "decisions", inspectionId ?? "all"],
    queryFn: () =>
      authedFetch(
        `/api/qc/decisions${inspectionId ? `?inspection_id=${encodeURIComponent(inspectionId)}` : ""}`,
      ).then((r) => json<QcDecision[]>(r)),
    refetchInterval: 15_000,
  });
}

export function useDefectCodes(activeOnly = false) {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["qc", "defect-codes", activeOnly],
    queryFn: () =>
      authedFetch(`/api/qc/defect-codes?active_only=${activeOnly}`).then((r) =>
        json<DefectCode[]>(r),
      ),
    staleTime: 30_000,
  });
}

export function useCreateDefectCode() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: DefectCodeCreate) => {
      const response = await authedFetch("/api/qc/defect-codes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<DefectCode>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["qc", "defect-codes"] }),
  });
}

export function useUpdateDefectCode() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      defectCode,
      payload,
    }: {
      defectCode: string;
      payload: DefectCodeUpdate;
    }) => {
      const response = await authedFetch(`/api/qc/defect-codes/${encodeURIComponent(defectCode)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<DefectCode>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["qc", "defect-codes"] }),
  });
}

export function useDeleteDefectCode() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (defectCode: string) => {
      const response = await authedFetch(`/api/qc/defect-codes/${encodeURIComponent(defectCode)}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(await errorMessage(response));
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["qc", "defect-codes"] }),
  });
}

export function useShifts(activeOnly = true) {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["catalog", "shifts", activeOnly],
    queryFn: () =>
      authedFetch(`/api/catalog/shifts?active_only=${activeOnly}`).then((r) => json<Shift[]>(r)),
    staleTime: 30_000,
  });
}

export function useCreateShift() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ShiftCreate) => {
      const response = await authedFetch("/api/catalog/shifts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<Shift>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["catalog", "shifts"] }),
  });
}

export function useUpdateShift() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ shiftId, payload }: { shiftId: string; payload: ShiftUpdate }) => {
      const response = await authedFetch(`/api/catalog/shifts/${encodeURIComponent(shiftId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<Shift>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["catalog", "shifts"] }),
  });
}

export function useDeleteShift() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (shiftId: string) => {
      const response = await authedFetch(`/api/catalog/shifts/${encodeURIComponent(shiftId)}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(await errorMessage(response));
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["catalog", "shifts"] }),
  });
}

export function useLots(activeOnly = true) {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["catalog", "lots", activeOnly],
    queryFn: () =>
      authedFetch(`/api/catalog/lots?active_only=${activeOnly}`).then((r) =>
        json<ProductionLot[]>(r),
      ),
    staleTime: 30_000,
  });
}

export function useCreateLot() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: LotCreate) => {
      const response = await authedFetch("/api/catalog/lots", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<ProductionLot>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["catalog", "lots"] }),
  });
}

export function useUpdateLot() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ lotId, payload }: { lotId: string; payload: LotUpdate }) => {
      const response = await authedFetch(`/api/catalog/lots/${encodeURIComponent(lotId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<ProductionLot>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["catalog", "lots"] }),
  });
}

export function useLotProducts(lotId: string) {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["catalog", "lots", lotId, "products"],
    queryFn: () =>
      authedFetch(`/api/catalog/lots/${encodeURIComponent(lotId)}/products`).then((r) =>
        json<LotProduct[]>(r),
      ),
    enabled: !!lotId,
    staleTime: 30_000,
  });
}

export function useAllocateLotProduct() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ lotId, payload }: { lotId: string; payload: LotProductAllocate }) => {
      const response = await authedFetch(
        `/api/catalog/lots/${encodeURIComponent(lotId)}/products`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      return json<LotProduct>(response);
    },
    onSuccess: (_, { lotId }) =>
      void queryClient.invalidateQueries({ queryKey: ["catalog", "lots", lotId, "products"] }),
  });
}

export function useStations(activeOnly = true) {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["catalog", "stations", activeOnly],
    queryFn: () =>
      authedFetch(`/api/catalog/stations?active_only=${activeOnly}`).then((r) =>
        json<Station[]>(r),
      ),
    staleTime: 30_000,
  });
}

/** Stations offered on the sign-up form. Deliberately bypasses authedFetch: the caller has no
 * account yet, so there is no token to send (backend/app/catalog_api.py list_station_options). */
export function useStationOptions(enabled = true) {
  return useQuery({
    queryKey: ["catalog", "station-options"],
    queryFn: () => fetch(`${API_BASE}/api/catalog/stations/options`).then((r) => json<StationOption[]>(r)),
    enabled,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useCreateStation() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: StationCreate) => {
      const response = await authedFetch("/api/catalog/stations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<Station>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["catalog", "stations"] }),
  });
}

export function useUpdateStation() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ stationId, payload }: { stationId: string; payload: StationUpdate }) => {
      const response = await authedFetch(`/api/catalog/stations/${encodeURIComponent(stationId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<Station>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["catalog", "stations"] }),
  });
}

export function useDeleteStation() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (stationId: string) => {
      const response = await authedFetch(`/api/catalog/stations/${encodeURIComponent(stationId)}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(await errorMessage(response));
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["catalog", "stations"] }),
  });
}

export function useProfiles() {
  const { authedFetch, role } = useAuth();
  return useQuery({
    queryKey: ["auth", "profiles"],
    queryFn: () => authedFetch("/api/auth/profiles").then((r) => json<Profile[]>(r)),
    enabled: role === "QC_SUPERVISOR",
    staleTime: 15_000,
  });
}

export function useUpdateProfile() {
  const { authedFetch } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, payload }: { userId: string; payload: ProfileUpdate }) => {
      const response = await authedFetch(`/api/auth/profiles/${encodeURIComponent(userId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return json<Profile>(response);
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["auth", "profiles"] }),
  });
}

export function useInspectionState(threadId: string | null) {
  const { authedFetch } = useAuth();
  return useQuery({
    queryKey: ["inspection", "state", threadId],
    queryFn: () => authedFetch(`/inspections/${threadId}/state`).then((r) => json<GraphRun>(r)),
    enabled: !!threadId,
    refetchInterval: (query) => (query.state.data?.status === "INTERRUPTED" ? false : 3_000),
  });
}
