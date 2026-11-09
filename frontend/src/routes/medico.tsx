import { createRoute, redirect } from "@tanstack/react-router";
import { DoctorWorkstationPage } from "@/features/consultation/pages/doctor-workstation-page";
import { getStoredDoctorSession, type StoredDoctorSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

export const medicoRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/medico",
  beforeLoad: () => {
    const doctorSession = getStoredDoctorSession();
    if (!doctorSession?.token) {
      throw redirect({ to: "/login" });
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
