import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import type { StoredManagerSession } from "@/lib/session-storage";
import { sessionTransport } from "@/lib/session-transport";
import { rootRoute } from "./root";

const LazyTelemetryDashboardPage = lazyRouteComponent(
  () => import("@/features/telemetry/pages/telemetry-dashboard-page"),
  "TelemetryDashboardPage",
);

const LazyProducaoBpaCard = lazyRouteComponent(
  () => import("@/features/ambulatory/components/producao-bpa-card"),
  "ProducaoBpaCard",
);

export const gestorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/gestor",
  beforeLoad: async () => {
    try {
      const staff = await sessionTransport.ensureStaffSession("GESTOR_UNIDADE");
      if (staff.role !== "GESTOR_UNIDADE") {
        throw redirect({ to: "/interno/login" });
      }
      return { managerSession: staff.managerSession };
    } catch {
      throw redirect({ to: "/interno/login" });
    }
  },
  component: function RouteComponent() {
    const { managerSession } = gestorRoute.useRouteContext() as {
      managerSession: StoredManagerSession;
    };
    return (
      <ClinicalPageLayout subtitle="Painel de Telemetria, Regulação e Produção Ambulatorial SUS">
        <Suspense fallback={<RoutePendingFallback />}>
          <LazyTelemetryDashboardPage
            managerSession={managerSession}
            renderBpaCard={
              <Suspense fallback={<RoutePendingFallback />}>
                <LazyProducaoBpaCard />
              </Suspense>
            }
          />
        </Suspense>
      </ClinicalPageLayout>
    );
  },
});
