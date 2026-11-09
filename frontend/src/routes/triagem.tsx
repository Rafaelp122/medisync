import { createRoute, redirect } from "@tanstack/react-router";
import { TriagemPage } from "@/features/onboarding/pages/triagem-page";
import {
  getStoredDoctorSession,
  getStoredManagerSession,
  getStoredSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

export const triagemRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/triagem",
  beforeLoad: () => {
    const session = getStoredSession();
    if (session?.atendimentoId) {
      throw redirect({ to: "/fila" });
    }

    const doctor = getStoredDoctorSession();
    if (doctor) {
      throw redirect({ to: "/medico" });
    }

    const manager = getStoredManagerSession();
    if (manager) {
      throw redirect({ to: "/gestor" });
    }
  },
  component: TriagemPage,
});
