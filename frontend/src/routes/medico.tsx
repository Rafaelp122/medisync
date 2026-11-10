import { createRoute, redirect } from "@tanstack/react-router";
import { silentRefreshToken } from "@/api/client";
import { DoctorWorkstationPage } from "@/features/consultation/pages/doctor-workstation-page";
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
      throw redirect({ to: "/login" });
    }
    if (!getAccessToken()) {
      await silentRefreshToken();
      if (!getAccessToken()) {
        clearStoredDoctorSession();
        throw redirect({ to: "/login" });
      }
    }
    return { doctorSession };
  },
  component: function RouteComponent() {
    const { doctorSession } = medicoRoute.useRouteContext() as {
      doctorSession: StoredDoctorSession;
    };
    return <DoctorWorkstationPage doctorSession={doctorSession} />;
  },
});
