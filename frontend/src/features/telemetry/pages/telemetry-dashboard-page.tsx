import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { client } from "@/api/client";
import { logoutApiV1AuthLogoutPost } from "@/api/generated/sdk.gen";
import { PainelGestor } from "@/features/telemetry/components/painel-gestor";
import { clearAccessToken } from "@/lib/auth-token";
import { clearStoredManagerSession, type StoredManagerSession } from "@/lib/session-storage";

export interface TelemetryDashboardPageProps {
  managerSession: StoredManagerSession;
  token?: string;
}

export function TelemetryDashboardPage({ managerSession, token }: TelemetryDashboardPageProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const handleManagerLogout = async () => {
    try {
      await logoutApiV1AuthLogoutPost({ client, body: {} });
    } catch {
      // Falha de rede não impede expurgo local
    }
    clearAccessToken();
    clearStoredManagerSession();
    queryClient.clear();
    navigate({ to: "/interno/login" });
  };

  return (
    <PainelGestor token={token} gestorNome={managerSession.nome} onLogout={handleManagerLogout} />
  );
}
