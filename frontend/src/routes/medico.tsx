import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import type { StoredDoctorSession } from "@/lib/session-storage";
import { sessionTransport } from "@/lib/session-transport";
import { rootRoute } from "./root";

const LazyDoctorWorkstationPage = lazyRouteComponent(
  () => import("@/features/consultation/pages/doctor-workstation-page"),
  "DoctorWorkstationPage",
);

const LazyProfessionalSchedulePanel = lazyRouteComponent(
  () => import("@/features/scheduling/components/professional-schedule-panel"),
  "ProfessionalSchedulePanel",
);

export const medicoRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/medico",
  beforeLoad: async () => {
    try {
      const staff = await sessionTransport.ensureStaffSession("MEDICO");
      if (staff.role !== "MEDICO") {
        throw redirect({ to: "/interno/login" });
      }
      return { doctorSession: staff.doctorSession };
    } catch {
      throw redirect({ to: "/interno/login" });
    }
  },
  component: function RouteComponent() {
    const { doctorSession } = medicoRoute.useRouteContext() as {
      doctorSession: StoredDoctorSession;
    };
    return (
      <ClinicalPageLayout subtitle="Estação Clínica do Profissional de Saúde">
        <Suspense fallback={<RoutePendingFallback />}>
          <LazyDoctorWorkstationPage
            doctorSession={doctorSession}
            renderSchedulePanel={
              <Suspense fallback={<RoutePendingFallback />}>
                <LazyProfessionalSchedulePanel />
              </Suspense>
            }
          />
        </Suspense>
      </ClinicalPageLayout>
    );
  },
});
