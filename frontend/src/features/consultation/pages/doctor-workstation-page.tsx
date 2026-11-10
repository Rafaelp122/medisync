import { useNavigate } from "@tanstack/react-router";
import { client } from "@/api/client";
import { logoutApiV1AuthLogoutPost } from "@/api/generated/sdk.gen";
import { DoctorWorkstation } from "@/features/consultation/components/doctor-workstation";
import { clearAccessToken, getAccessToken } from "@/lib/auth-token";
import { clearStoredDoctorSession, type StoredDoctorSession } from "@/lib/session-storage";

export interface DoctorWorkstationPageProps {
  doctorSession: StoredDoctorSession;
}

export function DoctorWorkstationPage({ doctorSession }: DoctorWorkstationPageProps) {
  const navigate = useNavigate();

  const handleDoctorLogout = async () => {
    try {
      await logoutApiV1AuthLogoutPost({ client, body: {} });
    } catch {
      // Falha de rede não impede expurgo local
    }
    clearAccessToken();
    clearStoredDoctorSession();
    navigate({ to: "/login" });
  };

  return (
    <div className="w-full max-w-[1600px] mx-auto">
      <DoctorWorkstation
        token={getAccessToken() ?? undefined}
        medicoId={doctorSession.medicoId}
        medicoNome={doctorSession.medicoNome}
        crmUf={doctorSession.crmUf}
        onLogout={handleDoctorLogout}
      />
    </div>
  );
}
