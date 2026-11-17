import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { client } from "@/api/client";
import { logoutApiV1AuthLogoutPost } from "@/api/generated/sdk.gen";
import { DoctorWorkstation } from "@/features/consultation/components/doctor-workstation";
import { clearAccessToken } from "@/lib/auth-token";
import { clearStoredDoctorSession, type StoredDoctorSession } from "@/lib/session-storage";

export interface DoctorWorkstationPageProps {
  doctorSession: StoredDoctorSession;
  token?: string;
  renderSchedulePanel?: ReactNode;
}

export function DoctorWorkstationPage({
  doctorSession,
  token,
  renderSchedulePanel,
}: DoctorWorkstationPageProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const handleDoctorLogout = async () => {
    try {
      await logoutApiV1AuthLogoutPost({ client, body: {} });
    } catch {
      // Falha de rede não impede expurgo local
    }
    clearAccessToken();
    clearStoredDoctorSession();
    queryClient.clear();
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
