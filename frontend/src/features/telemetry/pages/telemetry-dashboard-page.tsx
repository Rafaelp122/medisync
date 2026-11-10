import { useNavigate } from "@tanstack/react-router";
import { client } from "@/api/client";
import { logoutApiV1AuthLogoutPost } from "@/api/generated/sdk.gen";
import { PainelGestor } from "@/features/telemetry/components/painel-gestor";
import { clearAccessToken, getAccessToken } from "@/lib/auth-token";
import { clearStoredManagerSession, type StoredManagerSession } from "@/lib/session-storage";

export interface TelemetryDashboardPageProps {
  managerSession: StoredManagerSession;
}

export function TelemetryDashboardPage({ managerSession }: TelemetryDashboardPageProps) {
  const navigate = useNavigate();

  const handleManagerLogout = async () => {
    try {
      await logoutApiV1AuthLogoutPost({ client, body: {} });
    } catch {
      // Falha de rede não impede expurgo local
    }
    clearAccessToken();
    clearStoredManagerSession();
    navigate({ to: "/login" });
  };

  return (
    <PainelGestor
      token={getAccessToken() ?? undefined}
      gestorNome={managerSession.nome}
      onLogout={handleManagerLogout}
    />
  );
}
