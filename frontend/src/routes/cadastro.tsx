import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { ClinicalPageLayout } from "@/layouts/clinical-page-layout";
import {
  getStoredDoctorSession,
  getStoredManagerSession,
  getStoredSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

const LazyPatientRegisterPage = lazyRouteComponent(
  () => import("@/features/auth/pages/patient-register-page"),
  "PatientRegisterPage",
);

export const cadastroRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/cadastro",
  beforeLoad: () => {
    const session = getStoredSession();
    if (session?.token) {
      throw redirect({ to: session.atendimentoId ? "/fila" : "/home" });
    }

    const doctor = getStoredDoctorSession();
    if (doctor && (!doctor.papel || doctor.papel === "MEDICO")) {
      throw redirect({ to: "/medico" });
    }

    const manager = getStoredManagerSession();
    if (manager?.papel === "GESTOR_UNIDADE") {
      throw redirect({ to: "/gestor" });
    }
  },
  component: function CadastroRouteComponent() {
    return (
      <ClinicalPageLayout subtitle="Cadastro Rápido do Cidadão">
        <Suspense fallback={<RoutePendingFallback />}>
          <LazyPatientRegisterPage />
        </Suspense>
      </ClinicalPageLayout>
    );
  },
});
