import { createRoute, redirect } from "@tanstack/react-router";
import { OtpPage } from "@/features/onboarding/pages/otp-page";
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

    const doctor = getStoredDoctorSession();
    if (doctor) {
      throw redirect({ to: "/medico" });
    }

    const manager = getStoredManagerSession();
    if (manager) {
      throw redirect({ to: "/gestor" });
    }
  },
  component: OtpPage,
});
