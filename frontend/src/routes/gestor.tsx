import { createRoute, redirect } from "@tanstack/react-router";
import { TelemetryDashboardPage } from "@/features/telemetry/pages/telemetry-dashboard-page";
import { getStoredManagerSession, type StoredManagerSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

export const gestorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/gestor",
  beforeLoad: () => {
    const managerSession = getStoredManagerSession();
    if (!managerSession?.token) {
      throw redirect({ to: "/login" });
    }
    return { managerSession };
  },
  component: function RouteComponent() {
    const { managerSession } = gestorRoute.useRouteContext() as {
      managerSession: StoredManagerSession;
    };
    return <TelemetryDashboardPage managerSession={managerSession} />;
  },
});
