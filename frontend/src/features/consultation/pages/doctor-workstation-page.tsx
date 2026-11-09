import { useNavigate } from "@tanstack/react-router";
import { DoctorWorkstation } from "@/features/consultation/components/doctor-workstation";
import { clearStoredDoctorSession, type StoredDoctorSession } from "@/lib/session-storage";

export interface DoctorWorkstationPageProps {
  doctorSession: StoredDoctorSession;
}

export function DoctorWorkstationPage({ doctorSession }: DoctorWorkstationPageProps) {
  const navigate = useNavigate();

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
