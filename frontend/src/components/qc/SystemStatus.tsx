import { Dot } from "./primitives";
import { cn } from "@/lib/utils";
import { useAgentRuns, useAgentStatus } from "@/lib/queries";

const KNOWN_CAMERA_IDS = ["CAM-01", "CAM-02", "CAM-03", "CAM-04", "CAM-05"];

type Item = { name: string; value: string; state: "ok" | "warn" | "down" };

export function SystemStatusList({ compact = false }: { compact?: boolean }) {
  const { data: agentStatus, isError: statusError } = useAgentStatus();
  const { data: runs, isError: runsError } = useAgentRuns();

  const latestRun = runs?.[0];
  const usedCameras = new Set((latestRun?.state.camera_evidence ?? []).map((e) => e.camera_id));

  const items: Item[] = [
    {
      name: "AI ENGINE",
      value: statusError ? "MẤT KẾT NỐI" : agentStatus?.langgraph === "READY" ? "SẴN SÀNG" : "—",
      state: statusError ? "down" : agentStatus?.langgraph === "READY" ? "ok" : "warn",
    },
    {
      name: "CAMERA (LẦN GẦN NHẤT)",
      value: `${usedCameras.size}/${KNOWN_CAMERA_IDS.length} ĐÃ CHỤP`,
      state: usedCameras.size > 0 ? "ok" : "warn",
    },
    {
      name: "MÔ HÌNH THỊ GIÁC",
      value: agentStatus?.vision?.mode ?? "—",
      state: agentStatus?.vision?.configured ? "ok" : "warn",
    },
    {
      name: "AGENT SUY LUẬN",
      value: agentStatus?.reasoning?.mode ?? "—",
      state: agentStatus?.reasoning?.api_key_configured ? "ok" : "warn",
    },
    {
      name: "CƠ SỞ DỮ LIỆU",
      value: runsError ? "MẤT KẾT NỐI" : "ĐÃ KẾT NỐI",
      state: runsError ? "down" : "ok",
    },
  ];

  return (
    <ul className={cn("space-y-1.5", compact && "space-y-1")}>
      {items.map((s) => (
        <li key={s.name} className="flex items-center justify-between gap-2">
          <span className="label-caps">{s.name}</span>
          <span className="flex items-center gap-2 font-mono text-[11px] tracking-wider">
            <Dot state={s.state} />
            <span
              className={cn(
                s.state === "ok" && "text-success",
                s.state === "warn" && "text-warning",
                s.state === "down" && "text-destructive",
              )}
            >
              {s.value}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}
