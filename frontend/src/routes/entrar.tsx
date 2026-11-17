import { createRoute, redirect } from "@tanstack/react-router";
import { PatientAuthPage } from "@/features/auth/pages/patient-auth-page";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import {
  getStoredDoctorSession,
  getStoredManagerSession,
  getStoredSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

export const entrarRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/entrar",
  beforeLoad: () => {
    const session = getStoredSession();
    if (session?.token) {
      throw redirect({ to: session.atendimentoId ? "/fila" : "/home" });
    }

    const doctor = getStoredDoctorSession();
    if (doctor) throw redirect({ to: "/medico" });

    const manager = getStoredManagerSession();
    if (manager) throw redirect({ to: "/gestor" });
  },
  component: function EntrarRouteComponent() {
    return (
      <ClinicalPageLayout subtitle="Acesso do Cidadão ao Portal de Saúde SUS">
        <PatientAuthPage />
      </ClinicalPageLayout>
    );
  },
});
