import { useNavigate } from "@tanstack/react-router";
import { useDoctorLogout } from "@/features/consultation/api/use-doctor-logout";
import {
  DoctorWorkstation,
  type SchedulePanelRenderer,
} from "@/features/consultation/components/doctor-workstation";
import type { StoredDoctorSession } from "@/lib/session-storage";

export interface DoctorWorkstationPageProps {
  doctorSession: StoredDoctorSession;
  token?: string;
  renderSchedulePanel?: SchedulePanelRenderer;
}

export function DoctorWorkstationPage({
  doctorSession,
  token,
  renderSchedulePanel,
}: DoctorWorkstationPageProps) {
  const navigate = useNavigate();
  const logoutMutation = useDoctorLogout();

  const handleDoctorLogout = async () => {
    await logoutMutation.mutateAsync();
    navigate({ to: "/interno/login" });
  };

  return (
    <div className="w-full max-w-[1600px] mx-auto">
      <DoctorWorkstation
        token={token}
        medicoId={doctorSession.medicoId}
        medicoNome={doctorSession.medicoNome}
        crmUf={doctorSession.crmUf}
        onLogout={handleDoctorLogout}
        renderSchedulePanel={renderSchedulePanel}
      />
    </div>
  );
}
