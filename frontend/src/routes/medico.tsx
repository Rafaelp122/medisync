import { createRoute, redirect, useNavigate } from "@tanstack/react-router";
import { DoctorWorkstation } from "@/features/consultation/components/doctor-workstation";
import {
  clearStoredDoctorSession,
  getStoredDoctorSession,
  type StoredDoctorSession,
} from "@/lib/session-storage";
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
  component: MedicoPage,
});

function MedicoPage() {
  const navigate = useNavigate();
  const { doctorSession } = medicoRoute.useRouteContext() as {
    doctorSession: StoredDoctorSession;
  };

  const handleDoctorLogout = () => {
    clearStoredDoctorSession();
    navigate({ to: "/login" });
  };

  return (
    <div className="w-full max-w-[1600px] mx-auto">
      <DoctorWorkstation
        token={doctorSession.token}
        medicoId={doctorSession.medicoId}
        medicoNome={doctorSession.medicoNome}
        crmUf={doctorSession.crmUf}
        onLogout={handleDoctorLogout}
      />
    </div>
  );
}
