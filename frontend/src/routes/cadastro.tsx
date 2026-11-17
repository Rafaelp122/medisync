import { createRoute, redirect } from "@tanstack/react-router";
import { PatientRegisterPage } from "@/features/auth/pages/patient-register-page";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import {
  getStoredDoctorSession,
  getStoredManagerSession,
  getStoredSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

export const cadastroRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/cadastro",
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
  component: function CadastroRouteComponent() {
    return (
      <ClinicalPageLayout subtitle="Cadastro Rápido do Cidadão">
        <PatientRegisterPage />
      </ClinicalPageLayout>
    );
  },
});
