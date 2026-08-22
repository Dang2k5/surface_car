import { createFileRoute, Outlet } from "@tanstack/react-router";
import { SupervisorShell } from "@/components/supervisor/SupervisorShell";

export const Route = createFileRoute("/supervisor")({
  component: SupervisorLayout,
});

function SupervisorLayout() {
  return (
    <SupervisorShell>
      <Outlet />
    </SupervisorShell>
  );
}
