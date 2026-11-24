import { createRoute, redirect } from "@tanstack/react-router";
import {
  getStoredDoctorSession,
  getStoredManagerSession,
  getStoredSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

export const otpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/otp",
  beforeLoad: () => {
    const session = getStoredSession();
    if (session?.atendimentoId) {
      throw redirect({ to: "/fila" });
    }
    if (session?.token) {
      throw redirect({ to: "/home" });
    }

    const doctor = getStoredDoctorSession();
    if (doctor && (!doctor.papel || doctor.papel === "MEDICO")) {
      throw redirect({ to: "/medico" });
    }

    const manager = getStoredManagerSession();
    if (manager?.papel === "GESTOR_UNIDADE") {
      throw redirect({ to: "/gestor" });
    }

    throw redirect({ to: "/entrar" });
  },
});
