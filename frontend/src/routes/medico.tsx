import { createRoute, redirect } from "@tanstack/react-router";
import { silentRefreshToken } from "@/api/client";
import { DoctorWorkstationPage } from "@/features/consultation/pages/doctor-workstation-page";
import { ProfessionalSchedulePanel } from "@/features/scheduling/components/professional-schedule-panel";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import { getAccessToken } from "@/lib/auth-token";
import {
  clearStoredDoctorSession,
  getStoredDoctorSession,
  type StoredDoctorSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

export const medicoRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/medico",
  beforeLoad: async () => {
    const doctorSession = getStoredDoctorSession();
    if (!doctorSession) {
      throw redirect({ to: "/interno/login" });
    }
    if (!getAccessToken()) {
      await silentRefreshToken();
      if (!getAccessToken()) {
        clearStoredDoctorSession();
        throw redirect({ to: "/interno/login" });
      }
    }
    return { doctorSession };
  },
  component: function RouteComponent() {
    const { doctorSession } = medicoRoute.useRouteContext() as {
      doctorSession: StoredDoctorSession;
    };
    const token = getAccessToken() ?? undefined;
    return (
      <ClinicalPageLayout subtitle="Estação Clínica do Profissional de Saúde">
        <DoctorWorkstationPage
          doctorSession={doctorSession}
          renderSchedulePanel={<ProfessionalSchedulePanel token={token} />}
        />
      </ClinicalPageLayout>
    );
  },
});
