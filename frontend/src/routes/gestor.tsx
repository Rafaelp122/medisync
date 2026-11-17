import { createRoute, redirect } from "@tanstack/react-router";
import { silentRefreshToken } from "@/api/client";
import { TelemetryDashboardPage } from "@/features/telemetry/pages/telemetry-dashboard-page";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import { getAccessToken } from "@/lib/auth-token";
import {
  clearStoredManagerSession,
  getStoredManagerSession,
  type StoredManagerSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

export const gestorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/gestor",
  beforeLoad: async () => {
    const managerSession = getStoredManagerSession();
    if (!managerSession) {
      throw redirect({ to: "/interno/login" });
    }
    if (!getAccessToken()) {
      await silentRefreshToken();
      if (!getAccessToken()) {
        clearStoredManagerSession();
        throw redirect({ to: "/interno/login" });
      }
    }
    return { managerSession };
  },
  component: function RouteComponent() {
    const { managerSession } = gestorRoute.useRouteContext() as {
      managerSession: StoredManagerSession;
    };
    return (
      <ClinicalPageLayout subtitle="Painel de Telemetria, Regulação e Produção Ambulatorial SUS">
        <TelemetryDashboardPage managerSession={managerSession} />
      </ClinicalPageLayout>
    );
  },
});
