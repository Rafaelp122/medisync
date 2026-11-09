import { useNavigate } from "@tanstack/react-router";
import { PosConsultaSummary } from "@/features/consultation/components/pos-consulta-summary";
import {
  clearStoredCallData,
  clearStoredSession,
  type StoredPatientSession,
} from "@/lib/session-storage";

export interface PostConsultationPageProps {
  session: StoredPatientSession;
}

export function PostConsultationPage({ session }: PostConsultationPageProps) {
  const navigate = useNavigate();

  const handleNovaConsulta = () => {
    clearStoredSession();
    clearStoredCallData();
    navigate({ to: "/" });
  };

  return (
    <PosConsultaSummary
      atendimentoId={session.atendimentoId ?? ""}
      token={session.token}
      onNovaConsulta={handleNovaConsulta}
    />
  );
}
