import { useNavigate } from "@tanstack/react-router";
import { PosConsultaSummary } from "@/features/consultation/components/pos-consulta-summary";
import {
  clearStoredCallData,
  type StoredPatientSession,
  saveStoredSession,
} from "@/lib/session-storage";

export interface PostConsultationPageProps {
  session: StoredPatientSession;
}

export function PostConsultationPage({ session }: PostConsultationPageProps) {
  const navigate = useNavigate();

  const handleNovaConsulta = () => {
    saveStoredSession({
      token: session.token,
      pacienteId: session.pacienteId,
      role: session.role,
      tipo: session.tipo,
    });
    clearStoredCallData();
    navigate({ to: "/home" });
  };

  return (
    <PosConsultaSummary
      atendimentoId={session.atendimentoId ?? ""}
      token={session.token}
      onNovaConsulta={handleNovaConsulta}
    />
  );
}
