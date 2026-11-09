import { useNavigate } from "@tanstack/react-router";
import { PainelGestor } from "@/features/telemetry/components/painel-gestor";
import { clearStoredManagerSession, type StoredManagerSession } from "@/lib/session-storage";

export interface TelemetryDashboardPageProps {
  managerSession: StoredManagerSession;
}

export function TelemetryDashboardPage({ managerSession }: TelemetryDashboardPageProps) {
  const navigate = useNavigate();

  const handleManagerLogout = () => {
    clearStoredManagerSession();
    navigate({ to: "/login" });
  };

  return (
    <PainelGestor
      token={managerSession.token}
      gestorNome={managerSession.nome}
      onLogout={handleManagerLogout}
    />
  );
}
