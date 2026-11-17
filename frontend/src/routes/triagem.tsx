import { createRoute, redirect } from "@tanstack/react-router";
import { TriagemPage } from "@/features/onboarding/pages/triagem-page";
import { CitizenShellLayout } from "@/layouts/citizen-shell-layout";
import {
  getStoredDoctorSession,
  getStoredManagerSession,
  getStoredSession,
  type StoredPatientSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

export const triagemRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/triagem",
  beforeLoad: () => {
    const doctor = getStoredDoctorSession();
    if (doctor) {
      throw redirect({ to: "/medico" });
    }

    const manager = getStoredManagerSession();
    if (manager) {
      throw redirect({ to: "/gestor" });
    }

    const session = getStoredSession();
    if (!session?.token) {
      throw redirect({ to: "/entrar" });
    }

    if (session.atendimentoId) {
      throw redirect({ to: "/fila" });
    }

    return { session };
  },
  component: function TriagemRouteComponent() {
    const { session } = triagemRoute.useRouteContext() as { session: StoredPatientSession };
    return (
      <CitizenShellLayout session={session}>
        <TriagemPage />
      </CitizenShellLayout>
    );
  },
});
